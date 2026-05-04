from project.core.logic.db_calc import build_db_report_pieces
from project.config.workplace_config_provider import merge_db_and_csv_config
from project.config.count_per_loader import update_count_by_shift
from project.config.paths import MACHINE_CONFIG_PATH
from project.config.aliases import ORDER_ALIASES, GRUNDPROFIL_ALIASES, ARTICLE_ALIASES, GOOD_PRODUKTION_ALIASES
from project.config.db_loader import fetch_sap_basic_profiles, fetch_available_machines, fetch_orders_for_machines, normalize_db_df 
from project.core.logic.docx_export import export_report_docx
from project.core.logic.smart_matcher import SmartPlanMatcher
from project.config.paths import CONFING_PATH
from project.core.logic.scheduling import add_shifts, pl_weekday_name, round_shifts_custom
from pathlib import Path
from datetime import datetime, date
import pandas as pd
import traceback
import os
import tempfile
import re
import json

class MainController:
    def __init__(self, state, view):
        self.state = state
        self.view = view
        
    def handle_load_machines(self):
        # --- Pobranie konfiguracji (DB + CSV) ---
        df_cfg, source, missing = merge_db_and_csv_config(sync_missing_to_db=False)
        
        # --- Zapis do głównego stanu aplikacji ---
        self.state.machine_cfg = df_cfg
        self.state.machine_cfg_source = source
        
        try:
            machines = fetch_available_machines()
            
            # --- Jeśli część konfiguracji pochodziła z CSV, a nie z DB, zgłoś to widokowi ---
            if source == "db+csv":
                self.view.show_warning(
                    "Konfiguracja",
                    f"Konfiguracja: DB + CSV (brak w DB: {len(missing)})"
                )
                
            # --- Sukces połączenia co spowoduje wyświetlenie wyniku listy maszyn w popup
            self.view.show_machine_select_popup(machines, self.state.machine_cfg, self.on_machines_selected)
            
        except Exception as e:
            # --- Błąd (np. brak VPN / sterownika) -> polecenie dla widoku, aby wyświetlił błąd ---
            error_msg = f"Brak sterownika ODBC / brak dostępu do sieci firmowej.\n\nMożesz użyć trybu: Wczytaj plik (Excel)\n\nSzczegóły błędu:\n{str(e)}"
            self.view.show_error("Błąd połączenia:", error_msg)
            return
            
    # --- Obsługa wyboru maszyn ---
    def on_machines_selected(self, selected_machines, pps_by_machine, saturday_by_machine, sunday_by_machine, save_snapshot, changes, should_save_config):
        # --- jeśli użytkownik kliknął "TAK" na pytanie o zapis zmian ---
        if should_save_config and changes:
            df_mc_df = self.state.machine_cfg.copy()
            for m, _, new_val in changes:
                mask = df_mc_df["workplace"].astype("string").str.strip() == str(m).strip()
                if mask.any():
                    df_mc_df.loc[mask, "count_by_shift"] = int(new_val)
                else:
                    new_row = pd.DataFrame([{"workplace": str(m).strip(), "speed_m_per_min": 0.0, "count_by_shift": int(new_val)}])
                    df_mc_df = pd.concat([df_mc_df, new_row], ignore_index=True)

            self.state.machine_cfg = df_mc_df
            df_mc_df.to_csv(MACHINE_CONFIG_PATH, sep=";", index=False, encoding="utf-8") # Zapis do CSV
            
            # --- zapis do DB --- 
            if self.state.machine_cfg_source in ("db", "db+csv"):
                try:
                    for m, _, new_val in changes:
                        update_count_by_shift(m, new_val)
                except Exception as e:
                    self.view.show_warning("Uwaga", f"Zapisano do pliku CSV, ale błąd zapisu DB:\n{e}")
            
            # --- odświeżenie stanu ---
            df_cfg, source, missing = merge_db_and_csv_config(sync_missing_to_db=False)
            self.state.machine_cfg = df_cfg
            self.state.machine_cfg_source = source

        self.view.show_schedule_popup(
            lambda params: self._finish_db_calculation(
                selected_machines,
                pps_by_machine,
                saturday_by_machine,
                sunday_by_machine,
                save_snapshot,
                params,
            )
        )
    
    # --- Obsługa generowania raportu z pliku ---    
    def handle_generate_report(self):
        
        # --- sprawdzamy, czy jest dzisiejszy snapshot ---
        snap = self._load_snapshot_if_today()
        
        if not snap or not snap.get("end_by_machine"):
            # --- jeśli brak snapshotu, przerywamy i wyświetlamy popup informacyjny ---
            self.view.show_warning(
                "Brak porannego zapisu (Snapshot)",
                "Nie znaleziono zapisanych terminów zakończenia produkcji z dzisiejszą datą.\n\n"
                "Wykonaj poszczególne kroki:\n"
                "1) Wczytaj maszyny\n"
                "2) Przelicz produkcję wszystkich maszyn z zaznaczoną opcją 'Zapisz terminy'"
            )
            return  # <-- Blokada dalszego wykonania!

        # --- skoro mamy snapshot, zapisujemy daty do stanu aplikacji ---
        self.state.end_by_machine = snap["end_by_machine"]
        self.state.production_calculated = True
        
        # --- Poproś widok o ścieżkę do pliku ---
        file_path = self.view.ask_for_file_path(title="Wczytaj eksport Hydry (.xlsx/.csv)")
        
        # --- Zabezpieczenie przed anulowaniem ---
        if file_path is None: return
        
        # --- Jeśli mamy ścieżkę, przekaż ją do naszego nowego, wspólnego "silnika" ---
        self._load_hydra_file(file_path)
        
        # --- sprawdzmy czy wczytywanie się udało (czy stany nie są puste) ---
        if self.state.df_hydra is None or self.state.smart_plan_df is None:
        # --- wczytywanie padło (błąd został już wyświetlony przez _load_hydra_file) ---  
            return
        
        try:
            self.machines = fetch_available_machines()
        except Exception as e:
            self.view.show_error("Błąd generowania raportu", str(e))
            
        machines = sorted({machine.strip() for machine in self.machines if str(machine).strip()})
        
        self.view.show_report_params_popup(machines, self.on_report_params_selected)
    
    # --- Obsługa drukowania raportu ---               
    def handle_print_report(self):
        kind = self.state.last_report_kind

        # 1) Tryb SAP -> generujemy plik DOCX w locie z szablonu i wysyłamy do drukarki
        if kind == "sap" and self.state.last_report_data:
            try:
                # export_report_docx jest już u Ciebie poprawnie zaimportowane na górze pliku!
                docx_path = export_report_docx(self.state.last_report_data)
                self._print_docx(docx_path)
            except Exception as e:
                self.view.show_error("Błąd druku", f"Nie udało się wydrukować DOCX:\n{e}")
            return

        # 2) Tryb DB lub inny -> drukujemy skrócony tekst
        report_text_full = getattr(self.state, "last_report_text", "").strip()
        if kind == "db":
            report_to_print = self._make_print_summary(report_text_full)
        else:
            report_to_print = report_text_full

        if not report_to_print.strip():
            self.view.show_warning("Brak raportu", "Nie ma nic do wydrukowania.")
            return

        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w", encoding="utf-8") as f:
                f.write(report_to_print)
                path = f.name
            os.startfile(path, "print")
        except Exception as e:
            self.view.show_error("Błąd druku", f"Nie udało się uruchomić druku:\n{e}")

    # --- Obsługa edycji raportu DOCX ---        
    def handle_edit_report(self):
        kind = self.state.last_report_kind
        
        # Jeśli mamy raport SAP, generujemy plik DOCX i otwieramy go w programie Word
        if kind == "sap" and self.state.last_report_data:
            try:
                docx_path = export_report_docx(self.state.last_report_data)
                self._open_docx(docx_path)
            except Exception as e:
                self.view.show_error("Błąd edycji", f"Nie udało się wygenerować/otworzyć DOCX:\n{e}")
                traceback.print_exc()
        else:
            self.view.show_warning("Brak raportu", "Najpierw wygeneruj raport SAP.")
    
    # --- Obsługa czyszczenia raportu ---
    def handle_clean_text(self):
            print("Kontroler: Rozpoczynam czyszczenie raportu.")
            # --- zmieniamy stan aplikacji ---
            self.state.last_report_kind = None
            # --- Rozkazujemy widokowi posprzątać ekran ---
            self.view.clear_report_view()            
    
    # --- Główna funkcja obsługująca generowanie raportu po wybraniu parametrów przez użytkownika ---        
    def on_report_params_selected(self, params: dict):
            print(f"Kontroler otrzymał parametry od użytkownika: {params}")
            
            linia_value = params["linia"]
            start_order_id = params["start_order_id"]
            day_value = params["day"]
            
            # --- 1. Cięcie Hydry (OBOWIĄZKOWE) ---
            try:
                df_group = self._cut_from_order(self.state.df_hydra, start_order_id)
            except Exception as e:
                self.view.show_error("Błąd cięcia danych (Hydra)", str(e))
                traceback.print_exc()
                return

            # --- 2. Cięcie Smart Planu (OPCJONALNE / SMART MATCHING) ---
            df_cut_plan = None
            if self.state.smart_plan_df is not None:
                try:
                    df_cut_plan = self._cut_from_order(self.state.smart_plan_df, start_order_id)
                except Exception as e:
                    print(f"Uwaga: Brak zlecenia w Smart Planie. Wyłączam Smart Matching.")
                    self.view.show_warning(
                        "Ostrzeżenie Smart Plan", 
                        f"Plan nie pasuje do startowego zlecenia.\nRaport wygeneruje się bez inteligentnego dopasowania (Fallback).\n\nSzczegóły: {str(e)}"
                    )
                    df_cut_plan = None

            # --- 3. Pobieranie SAP ---
            try:
                df_sap = fetch_sap_basic_profiles(linia=linia_value, day=day_value)
                if df_sap is None or df_sap.empty:
                    raise ValueError(f"Nie znaleziono danych SAP dla linii: {linia_value} w dniu: {day_value}")
            except Exception as e:
                self.view.show_error("Błąd pobierania danych SAP", str(e))
                return

            # --- 4. Uruchomienie silnika SmartPlanMatcher ---
            try:
                matcher = SmartPlanMatcher(df_group, df_cut_plan, df_sap)
                wynik = matcher.run_matching()
                
                blocks = wynik["blocks"]
                lines = wynik["lines"]
                rows = wynik["rows"]
                missing_articles = wynik["missing_articles"]
                
            except Exception as e:
                self.view.show_error("Błąd generowania raportu (Smart Matcher)", str(e))
                traceback.print_exc()
                return
                
            # --- 5. Logowanie do konsoli (zostawiamy dla testów) ---
            print("\n=== Kolejność podstaw (Hydra) ===")
            for i, b in enumerate(blocks):
                print(f'{i+1}. {b["gp"]} ({b["side"]})')
            print("=================================\n")
            
            # --- DODANE: Pobranie brakujących danych ---
            sap_user = wynik.get("sap_user", "")
            shift_info = self._get_shift_info_from_snapshot(linia_value)

            # --- Przekazanie DANYCH do Widoku ---
            # Przekazujemy również sap_user, aby pokazał się w GUI!
            self.view.render_sap_report_table(linia_value, day_value, rows, sap_user)
            
            # (Opcjonalnie) aktualizacja stanu
            self.state.last_report_kind = "sap"
            self.view.set_print_button_visibility(True)

            # --- Przygotowanie nazwy maszyny dla Pylance ---
            machine_match = re.search(r'(\d+)\s*$', linia_value)
            machine_name = f"Maszyna {int(machine_match.group(1))}" if machine_match else ""

            # --- Zapis danych do stanu (potrzebne do druku DOCX) ---
            self.state.last_report_data = {
                "shift_info": shift_info, 
                "report_date": str(date.today()),
                "user": sap_user, 
                "line": linia_value,
                "machine": machine_name,
                "rows": [
                    {
                        "lp": r["lp"],
                        "index": r["index"],
                        "qty_m": f'{r["qty"]:.1f} {r["jm"]}',
                        "pcs": str(r["szt"]),
                        "pallets": "",
                    }
                    for r in rows
                ]
            }

            # --- 6. Obsługa ostrzeżeń (brak 0022) ---
            if missing_articles:
                preview = "\n".join([f"• {a}: brakuje strony 0022" for a in missing_articles[:12]])
                if len(missing_articles) > 12:
                    preview += f"\n… i jeszcze {len(missing_articles) - 12} kolejnych."

                self.view.show_warning(
                    "Uwaga: braki strony 0022",
                    f"Wykryto konflikt: na liście artykułów brakuje strony wewnętrznej 0022.\n\nSzczegóły:\n{preview}"
                )
    
    # --- pomocniecze funkcje do obsługi raportu z pliku ---        
    def _load_hydra_file(self, file_path: str):
        """Główny menedżer wczytywania pliku. Czyta plik raz, a potem deleguje zadania."""
        try:
            # --- ddczyt surowego pliku --- 
            ext = Path(file_path).suffix.lower()
            
            if ext in (".xlsx", ".xls"):
                self.df_raw = pd.read_excel(file_path, engine="openpyxl", header=1)
            elif ext == ".csv":
                self.df_raw = pd.read_csv(file_path, encoding="utf-8-sig", sep=",", low_memory=False)
            else:               
                raise ValueError("Nieobsługiwany format pliku. Wybierz .xlsx, .xls lub .csv")
            
            if self.df_raw is None or self.df_raw.empty:
                raise ValueError("Plik jest pusty lub nie udało się go odczytać.")

            # --- Czyszczenie nagłówków (usuwanie twardych spacji) ---
            self.df_raw.columns = [" ".join(str(c).replace("\xa0", " ").strip().split()) for c in self.df_raw.columns]
            self.df_raw.columns = [str(c).strip() for c in self.df_raw.columns]
            
            # --- Przekazanie do podwykonawców ---
            df_hydra_queue = self._extract_hydra_queue(self.df_raw)
            df_smart_plan = self._extract_smart_plan(self.df_raw)
            
            # --- Zapis do stanu ---
            self.state.df_hydra = df_hydra_queue
            self.state.smart_plan_df = df_smart_plan
            
            # --- Test w konsoli do diagnozy ---
            """
            print("Kontroler: Plik załadowany pomyślnie!")
            print(f"Ilość wierszy kolejki Hydry: {len(df_hydra_queue) if df_hydra_queue is not None else 0}")
            print(f"Ilość wierszy Smart Planu: {len(df_smart_plan ) if df_smart_plan is not None else 0}")
            """
        except Exception as e:
            self.view.show_error("Błąd wczytywania pliku", str(e))   
    
    # --- podwykonawcy do obsługi raportu z pliku ---
    def _extract_hydra_queue(self, df: pd.DataFrame) -> pd.DataFrame:
            # --- Użyj detektorów, aby znaleźć dokładne nazwy kolumn w pliku ---
            order_col = self._find_column(df, ORDER_ALIASES)
            article_col = self._find_column(df, ARTICLE_ALIASES)
            gp_col = self._find_column(df, GRUNDPROFIL_ALIASES)
            side_col = self._detect_side_column(df)

            # --- Wytnij z df tylko te 4 kolumny (.copy()) ---
            out = df[[order_col, article_col, gp_col, side_col]].copy()
            out = out.rename(columns={
            order_col: "order_id",
            article_col: "article",
            gp_col: "grundprofil",
            side_col: "side",
            })
            
            out["order_id"] = out["order_id"].astype("string").str.strip()
            out["article"] = out["article"].astype("string").str.strip()
            out["grundprofil"] = out["grundprofil"].astype("string").str.strip()

            out = out[(out["order_id"] != "") & (out["article"] != "") & (out["grundprofil"] != "")]
        
            return out.reset_index(drop=True)
    
    # --- ta funkcja służy do wyciągania danych ze Smart Planu, ale jest bardziej elastyczna i odporna na brak kolumn. Jeśli plik nie ma kolumn potrzebnych do Smart Planu, zwraca None, a program będzie działał dalej w trybie awaryjnym (fallback). ---    
    def _extract_smart_plan(self, df: pd.DataFrame) -> pd.DataFrame | None:
            """Podwykonawca 2: Wyciąga metry, sztuki i status wykonania. Jeśli plik tego nie ma, zwraca None."""
            try:
                needed_fixed = [
                    "Stanowisko robocze", "Artykuł", "Docelowa wartość (P)",
                    "Jednostka (P)", "Docelowa wartość (S)", "Jednostka (S)", "Rodzaj zlecenia"
                ]

                # --- Szukamy opcjonalnej kolumny 'dobrej produkcji' ---
                good_p_col = None
                try:
                    # Szukamy w df, a nie w df.columns!
                    good_p_col = self._find_column(df, GOOD_PRODUKTION_ALIASES)
                    needed_fixed.insert(3, good_p_col)
                except ValueError:
                    pass  # Zignoruj, jeśli plik nie ma tej kolumny

                # --- Szukamy kolumn zleceń ---
                zlecenie_cols = [c for c in df.columns if c.startswith("Zlecenie")]
                if len(zlecenie_cols) < 2:
                    raise ValueError("Brakuje drugiej kolumny 'Zlecenie' (tej ze stroną).")

                df_tmp = df[needed_fixed + zlecenie_cols].copy()
                side_col = self._detect_side_column(df_tmp)

                order_cols = [c for c in zlecenie_cols if c != side_col]
                if not order_cols:
                    raise ValueError("Nie znalazłem kolumny z numerem zlecenia.")
                order_col = order_cols[0]

                # --- Wycinanie docelowego DataFrame ---
                out = df[needed_fixed + [order_col, side_col]].copy()

                rename_map = {
                    "Stanowisko robocze": "workplace",
                    "Artykuł": "profile",
                    "Docelowa wartość (P)": "target_value_p",
                    "Jednostka (P)": "unit_p",
                    "Docelowa wartość (S)": "target_value_s",
                    "Jednostka (S)": "unit_s",
                    "Rodzaj zlecenia": "order_type",
                    order_col: "order_id",
                    side_col: "side",
                }
                if good_p_col:
                    rename_map[good_p_col] = "good_qty_p"

                out = out.rename(columns=rename_map)

                # --- Normalizacja liczb ---
                for col in ("target_value_p", "target_value_s", "good_qty_p"):
                    if col in out.columns:
                        out[col] = (
                            out[col].astype(str)
                            .str.replace("\xa0", "", regex=False)
                            .str.replace(" ", "", regex=False)
                            .str.replace(",", ".", regex=False)
                        )
                        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)

                # Jeśli kolumny wykonania nie było od początku, tworzymy ją z zerami
                if "good_qty_p" not in out.columns:
                    out["good_qty_p"] = 0.0

                out["order_id"] = out["order_id"].astype("string").str.strip().str.replace(r"\.0$", "", regex=True)

                return out

            except Exception as e:
                print(f"Kontroler: Plik nie zawiera pełnego 'Smart Planu'. Ostrzeżenie: {e}")
                return None        
    
    # --- ta funkcja jest głównym menedżerem, który po otrzymaniu parametrów od użytkownika, pobiera dane z DB i generuje raport. ---
    def _finish_db_calculation(
        self, 
        selected_machines: list[str], 
        pps_by_machine: dict[str, int], 
        saturday_by_machine: dict[str, bool], 
        sunday_by_machine: dict[str, bool], 
        save_snapshot_flag: bool,  # <--- DODANE: odbieramy flagę
        params: dict
        ):
        """Ta funkcja odpali się, gdy użytkownik kliknie OK w popupie z wyborem daty i zmiany."""
        # --- przetwarzamy parametry z drugiego popupu (Harmonogramu) ---
        s_shift = params["start_shift"]
        
        if params["start_mode"] == "today":
            s_date = date.today()
        else:
            s_date = datetime.strptime(params["start_date"], "%Y-%m-%d").date()

        try:
            df_raw = fetch_orders_for_machines(selected_machines)
            df_profiles = pd.read_csv(CONFING_PATH, sep=";", encoding="utf-8")
            
            if df_raw is None or df_raw.empty:
                self.view.show_warning("Brak danych", "Baza SQL nie zwróciła żadnych zleceń.")
                return   
                     
            df_orders = normalize_db_df(df_raw)
            
            if df_orders is None or df_orders.empty:
                self.view.show_warning("Brak danych", "Baza SQL nie zwróciła żadnych zleceń dla tych maszyn.")
                return

            # --- wywołujemy nasz silnik obliczeń z db_calc.py ---
            report_text = build_db_report_pieces(
                df=df_orders,
                df_cfg=df_profiles,
                selected_machines=selected_machines,
                pps_by_machine=pps_by_machine,
                start_d=s_date,
                start_shift=s_shift,
                saturday_by_machine=saturday_by_machine,
                sunday_by_machine=sunday_by_machine,
            )

            # --- wyświetlamy raport w głównym oknie ---
            self.state.last_report_text = report_text 
            self.view.render_db_report_cards(report_text)
            
            self.state.last_report_kind = "db"
            self.view.set_print_button_visibility(True)

            # --- wyciągamy z wygenerowanego tekstu raportu daty zakończenia poszczególnych maszyn ---
            end_by_machine = {}
            current_machine = None

            for line in report_text.splitlines():
                m = re.match(r"^===\s*(.+?)\s*===$", line.strip())
                if m:
                    current_machine = m.group(1).strip()
                    continue

                if current_machine and line.strip().startswith("Przewidywana produkcja do:"):
                    end_by_machine[current_machine] = line.strip()

            # Zapisujemy do stanu aplikacji
            self.state.end_by_machine = end_by_machine
            self.state.production_calculated = True
            
            # Jeśli user zaznaczył "Zapisz terminy" (save_snapshot_flag), zapisujemy na dysk (%APPDATA%)
            if save_snapshot_flag:
                self.save_snapshot(
                    end_by_machine=end_by_machine,
                    meta={
                        "selected_machines": selected_machines,
                        "info": "Poranny snapshot z harmonogramu produkcji"
                    }
                )

        except Exception as e:
            self.view.show_error("Błąd obliczeń", f"Wystąpił problem podczas generowania raportu:\n{e}")
            traceback.print_exc()
            
    def handle_confirm_order(self):
        try:
            # 1. Wybór pliku
            file_path = self.view.ask_for_file_path(title="Wybierz plik (Excel/CSV)")
            if not file_path: return

            # 2. Wczytanie pliku naszym menedżerem (wyciągnie od razu Smart Plan)
            self._load_hydra_file(file_path)
            df = self.state.smart_plan_df

            if df is None or df.empty:
                self.view.show_error("Brak danych", "Nie udało się wyciągnąć planu produkcji z wybranego pliku.")
                return

            # 3. Zlecenie od usera
            order_id = self.view.ask_order_id_popup()
            if not order_id: return

            # 4. Utnij dane od początku do wskazanego zlecenia (włącznie)
            try:
                df_cut = self._cut_until_order(df, order_id)
            except Exception as e:
                self.view.show_error("Nie znaleziono zlecenia", str(e))
                return

            # 5. Sprawdź maszynę (musi być jedna)
            workplaces = df_cut["workplace"].dropna().astype("string").str.strip().unique()
            if len(workplaces) != 1:
                self.view.show_error("Wybór maszyny", f"W danych wykryto wiele maszyn: {list(workplaces)}")
                return
            workplace = workplaces[0]

            # 6. Wczytanie konfiguracji maszyny
            # --- POPRAWKA: Ładujemy konfigurację maszyn, jeśli w pamięci programu jest pusta ---
            if self.state.machine_cfg is None or self.state.machine_cfg.empty:
                df_cfg_mc, source, missing = merge_db_and_csv_config(sync_missing_to_db=False)
                self.state.machine_cfg = df_cfg_mc
                self.state.machine_cfg_source = source

            df_mc = self.state.machine_cfg
            if df_mc is None or df_mc.empty:
                self.view.show_error("Brak konfiguracji", "Nie udało się wczytać konfiguracji maszyn.")
                return

            row = df_mc.loc[df_mc["workplace"].astype("string").str.strip() == str(workplace).strip()]
            if row.empty:
                self.view.show_error("Brak konfiguracji", f"Nie znaleziono maszyny '{workplace}' w konfiguracji.")
                return
            
            default_speed = float(row.iloc[0]["speed_m_per_min"])
            default_pps = int(row.iloc[0]["count_by_shift"])

            # 7. Zapytaj usera o tryb obliczeń (kolejny Popup)
            choice = self.view.ask_calc_mode_popup(workplace, default_speed, default_pps)
            if not choice: return

            # 8. Opcjonalny zapis zmienionych parametrów maszyny
            mask = df_mc["workplace"].astype("string").str.strip() == str(workplace).strip()
            if choice["mode"] == "speed":
                new_speed = float(choice["speed_m_per_min"])
                if abs(new_speed - default_speed) > 1e-9:
                    if self.view.show_yes_no("Zapis do konfiguracji", "Zmieniono prędkość. Zapisać zmiany?"):
                        df_mc.loc[mask, "speed_m_per_min"] = new_speed
                        df_mc.to_csv(MACHINE_CONFIG_PATH, sep=";", index=False, encoding="utf-8")
                        self.state.machine_cfg = df_mc
            elif choice["mode"] == "shift":
                new_pps = int(choice["pieces_per_shift"])
                if new_pps != default_pps:
                    if self.view.show_yes_no("Zapis do konfiguracji", "Zmieniono szt./zmianę. Zapisać zmiany?"):
                        df_mc.loc[mask, "count_by_shift"] = new_pps
                        df_mc.to_csv(MACHINE_CONFIG_PATH, sep=";", index=False, encoding="utf-8")
                        self.state.machine_cfg = df_mc

            # 9. Skomplikowana kalkulacja wyników (Teraz zwraca słownik z danymi!)
            df_cfg = pd.read_csv(CONFING_PATH, sep=";", encoding="utf-8")
            result_data = self._calculate_confirmation_result(df_cut, df_cfg, workplace, order_id, choice)

            # 10. Wyświetlenie wyniku na specjalnej Karcie
            if result_data:
                self.state.last_report_kind = None  
                self.view.set_print_button_visibility(False)
                self.view.render_order_confirmation_card(result_data) # <--- ZMIANA NA NOWĄ METODĘ

        except Exception as e:
            # PANCERNA OSŁONA: Jeśli cokolwiek wybuchnie, program pokaże okienko, a nie tylko zniknie!
            self.view.show_error("Nieoczekiwany błąd", f"Wystąpił problem:\n{e}")
            traceback.print_exc()
        

    # # # # # # # # # # # # # # # # # # # # # # # #
    # NARZĘDZIA POMOCNICZE DO SZUKANIA KOLUMN     #
    # # # # # # # # # # # # # # # # # # # # # # # #

    def _norm(self, text: str) -> str:
        return " ".join(str(text).replace("\xa0", " ").strip().lower().split())

    def _contains_any(self, cell_text: str, aliases: list[str]) -> bool:
        t = self._norm(cell_text)
        return any(a in t for a in aliases)

    def _find_column(self, df: pd.DataFrame, aliases: list[str]) -> str:
        for col in df.columns:
            if self._contains_any(col, aliases):
                return col
        raise ValueError(f"Nie znalazłem kolumny pasującej do aliasów: {aliases}")

    def _detect_side_column(self, df: pd.DataFrame) -> str:
        allowed = {"0020", "0021", "0022", "0023"}
        for col in df.columns:
            s = df[col].astype("string").str.strip().str.replace(r"\.0$", "", regex=True).str.zfill(4)
            non_empty = s[s != ""]
            if non_empty.empty:
                continue
            if non_empty.isin(allowed).mean() > 0.8:
                return col
        raise ValueError("Nie znaleziono kolumny strony (20/21/22/23).")
    
    def _normalize_order_id(self, s: str) -> str:
        """Czyści numer zlecenia z zer wiodących i końcówek .0"""
        s = str(s).strip()
        import re
        s = re.sub(r"\.0$", "", s)
        s = s.lstrip("0")
        return s if s != "" else "0"

    def _cut_from_order(self, df: pd.DataFrame, start_order_id: str) -> pd.DataFrame:
        """Obcina DataFrame od podanego zlecenia (włącznie) do końca."""
        if "order_id" not in df.columns:
            raise ValueError("Brak kolumny order_id w danych.")

        start_norm = self._normalize_order_id(start_order_id)

        tmp = df.copy()
        tmp["_order_norm"] = tmp["order_id"].astype("string").apply(self._normalize_order_id)

        hits = tmp.index[tmp["_order_norm"] == start_norm].tolist()
        
        if not hits:
            # --- tworzymy próbkę pierwszych zleceń do komunikatu błędu ---
            sample = tmp["order_id"].astype("string").head(10).tolist()
            raise ValueError(
                f"Nie znaleziono startowego zlecenia: {start_order_id}\n"
                f"(pierwsze zlecenia w pliku to np.: {sample})"
            )

        # Zwraca DataFrame od pierwszego trafienia do samego końca
        return df.loc[hits[0]:].reset_index(drop=True)
    
    # def _build_blocks(self, df: pd.DataFrame) -> list[dict]:
    #     """Grupuje ciągłe zlecenia o tym samym grundprofil i side w bloki."""
    #     tmp = df.copy()
    #     tmp["grundprofil"] = tmp["grundprofil"].astype("string").str.strip()
    #     tmp["side"] = tmp["side"].astype("string").str.strip().str.zfill(4)
        
    #     # Opcjonalna normalizacja zer wiodących na potrzeby grupowania
    #     mask = tmp["order_id"].str.fullmatch(r"\d+").fillna(False) & (tmp["order_id"].str.len() < 12)
    #     tmp.loc[mask, "order_id"] = tmp.loc[mask, "order_id"].str.zfill(12)

    #     blocks: list[dict] = []
    #     prev = None
    #     start = 0
    #     keys = list(zip(tmp["grundprofil"].tolist(), tmp["side"].tolist()))

    #     for i, key in enumerate(keys):
    #         if key != prev:
    #             if prev is not None:
    #                 b = tmp.iloc[start:i]
    #                 blocks.append({
    #                     "gp": prev[0],
    #                     "side": prev[1],
    #                     "order_ids": set(b["order_id"].tolist()),
    #                     "start_i": start,
    #                     "end_i": i - 1,
    #                 })
    #             prev = key
    #             start = i

    #     if prev is not None and len(tmp) > 0:
    #         b = tmp.iloc[start:]
    #         blocks.append({
    #             "gp": prev[0],
    #             "side": prev[1],
    #             "order_ids": set(b["order_id"].tolist()),
    #             "start_i": start,
    #             "end_i": len(tmp) - 1,
    #         })
            
    #     return blocks
    
    # --- tworzy skrócony raport do druku z pełnego raportu tylko kluczowe informacje ---
    def _make_print_summary(self, report_text: str) -> str:
        if not report_text or not report_text.strip():
            return ""

        lines = report_text.splitlines()
        out: list[str] = []
        current_machine: str | None = None
        current_end: str | None = None

        for line in lines:
            line = line.strip()

            # nagłówek maszyny
            m = re.match(r"^===\s*(WLO-[A-Z]\d{3})\s*===$", line)
            if m:
                # jeśli kończymy poprzednią maszynę
                if current_machine:
                    out.append(f"=== {current_machine} ===")
                    out.append(current_end or "Przewidywana produkcja do: brak danych")
                    out.append("")  # pusta linia między maszynami
                current_machine = m.group(1)
                current_end = None
                continue

            # linia końca produkcji
            if line.startswith("Przewidywana produkcja do:"):
                current_end = line

            # jeśli maszyna nie ma danych
            if line == "Brak danych." and current_machine:
                current_end = "Przewidywana produkcja do: brak danych"

        # domknij ostatnią maszynę
        if current_machine:
            out.append(f"=== {current_machine} ===")
            out.append(current_end or "Przewidywana produkcja do: brak danych")
            out.append("")

        title = "---- Przewidywane zakończenie produkcji --- \n\n"
        return title + "\n".join(out).rstrip() + "\n"  

    def _open_docx(self, path: Path) -> None:
        try:
            os.startfile(str(path))
        except Exception as e:
            self.view.show_error("Błąd", f"Nie udało się otworzyć pliku:\n{e}")  
            
    def _print_docx(self, path: Path) -> None:
        try:
            os.startfile(str(path), "print")  # Windows
        except Exception as e:
            self.view.show_error("Błąd druku", f"Nie udało się uruchomić druku:{e}")        
    
    def _get_shift_info_from_snapshot(self, linia: str) -> str:
        """Pobiera informację o dacie zakończenia dla danej linii z pliku snapshot.json."""
        try:
            # Domyślna ścieżka %APPDATA%\ProductionCounter
            base = Path(os.getenv("APPDATA") or Path.home())
            snap_path = base / "ProductionCounter" / "production_snapshot.json"
            
            if not snap_path.exists():
                return f"{date.today().strftime('%d.%m.%Y')} (zmiana 1) - brak zapisu"
            
            with open(snap_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            # Sprawdzamy czy snapshot jest z dzisiaj
            if data.get("snapshot_date") != date.today().isoformat():
                return f"{date.today().strftime('%d.%m.%Y')} (zmiana 1) - stary zapis z {data.get('snapshot_date')}"
                
            end_by_machine = data.get("end_by_machine", {})
            shift_line = end_by_machine.get(linia)
            
            if shift_line:
                # Obcinamy tekst "Przewidywana produkcja do:" z początku stringa
                return shift_line.replace("Przewidywana produkcja do:", "").strip()
                
        except Exception as e:
            print(f"Błąd odczytu snapshotu: {e}")
            
        return f"{date.today().strftime('%d.%m.%Y')} (zmiana 1) - błąd odczytu"
    
    # --- OBSŁUGA SNAPSHOTÓW (ZAPIS / WCZYTYWANIE) ---

    def _get_app_data_dir(self) -> Path:
        # --- zwraca i w razie potrzeby tworzy folder aplikacji w %APPDATA%.---
        base = Path(os.getenv("APPDATA") or Path.home())
        app_dir = base / "ProductionCounter"
        app_dir.mkdir(parents=True, exist_ok=True)
        return app_dir

    def _snapshot_path(self) -> Path:
        # --- zwraca pełną ścieżkę do pliku snapshotu. ---
        return self._get_app_data_dir() / "production_snapshot.json"

    def save_snapshot(self, end_by_machine: dict[str, str], meta: dict | None = None) -> None:
        # --- zapisuje wyliczone daty zakończenia do pliku JSON. ---
        path = self._snapshot_path()
        today = date.today().isoformat()
        
        if path.exists():
            try:
                content = path.read_text(encoding="utf-8")
                if content.strip(): # Sprawdzamy czy plik nie jest pusty
                    existing = json.loads(content)
                    if existing.get("snapshot_date") == today:
                        # Teraz ta metoda już istnieje w widoku!
                        ok = self.view.show_yes_no(
                            "Snapshot już istnieje",
                            "Snapshot na dzisiaj już istnieje.\nCzy chcesz go nadpisać?"
                        )
                        if not ok:
                            return
            except json.JSONDecodeError:
                pass

        # --- konstrukcja payloadu ---
        payload = {
            "snapshot_date": today,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "end_by_machine": end_by_machine,
            "meta": meta or {},
        }
        
        # --- zapis do pliku (zastępuje stary plik z tego samego dnia bez pytania) --- 
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_snapshot_if_today(self) -> dict | None:
        # --- ładuje snapshot tylko jeśli pochodzi z dzisiejszego dnia. W przeciwnym razie zwraca None. ---
        path = self._snapshot_path()
        if not path.exists():
            return None

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

        # --- walidacja daty - musi być z dzisiaj ---
        if data.get("snapshot_date") != date.today().isoformat():
            return None

        return data
    
    def _cut_until_order(self, df: pd.DataFrame, order_id: str) -> pd.DataFrame:
        """Obcina DataFrame od początku do podanego zlecenia (włącznie)."""
        if "order_id" not in df.columns:
            raise ValueError("Brak kolumny order_id w danych.")

        want = self._normalize_order_id(order_id)
        tmp = df.copy()
        tmp["_ord_norm"] = tmp["order_id"].astype("string").apply(self._normalize_order_id)

        hits = tmp.index[tmp["_ord_norm"] == want].tolist()
        if not hits:
            sample = tmp["order_id"].head(10).tolist()
            raise ValueError(f"Nie znaleziono zlecenia: {order_id}\n(pierwsze zlecenia to np.: {sample})")

        last_idx = hits[-1]
        return df.loc[:last_idx].reset_index(drop=True)

    def _calculate_confirmation_result(self, dfx: pd.DataFrame, df_cfg: pd.DataFrame, workplace: str, order_id: str, choice: dict) -> dict:
        """Silnik liczący czas dla Potwierdzenia Zlecenia."""
        df_cfg["profile"] = df_cfg["profile"].astype("string").str.strip()
        df_cfg["side"] = df_cfg["side"].astype("string").str.strip().str.zfill(4)
        df_cfg["setting_time"] = pd.to_numeric(df_cfg["setting_time"], errors="coerce")
        
        profile_col = "profile_full" if "profile_full" in dfx.columns else "profile"
        dfx["profile"] = dfx[profile_col].astype("string").str.strip().str.split("-", n=1).str[0]
        if "side" not in dfx.columns:
            dfx["side"] = "0021" # Default
        else:
            dfx["side"] = dfx["side"].astype("string").str.strip().str.replace(r"\.0$", "", regex=True).str.zfill(4)

        dfx = dfx.merge(df_cfg[["profile", "side", "setting_time"]], on=["profile", "side"], how="left")
        
        dfx.loc[dfx["side"] == "0020", "setting_time"] = 0

        # Metry pozostałe (Z poprawką pd.Series aby uniknąć błędu fillna)
        target_p = pd.to_numeric(dfx.get("target_value_p", pd.Series(0.0, index=dfx.index)), errors="coerce").fillna(0.0)
        good_p = pd.to_numeric(dfx.get("good_qty_p", pd.Series(0.0, index=dfx.index)), errors="coerce").fillna(0.0)
        unit = dfx.get("unit_p", pd.Series(["M"]*len(dfx))).astype("string").str.strip().str.upper()

        remaining_p = target_p.copy()
        mask_started = good_p > 0
        remaining_p.loc[mask_started] = (target_p - good_p).clip(lower=0.0)
        dfx["length_m"] = remaining_p.where(unit == "M", 0.0)
        total_m = float(dfx["length_m"].sum())

        # Sztuki (Z poprawką pd.Series)
        pieces = pd.to_numeric(dfx.get("target_value_s", pd.Series(0.0, index=dfx.index)), errors="coerce").fillna(0.0)
        total_pieces = float(pieces.sum())

        # --- ZBROJENIA: liczymy ZMIANY w kolejności (plik zachowuje bloki!) ---
        keys = list(zip(
            dfx["profile"].astype("string").str.strip(),
            dfx["side"].astype("string").str.strip().str.zfill(4)
        ))

        setup_count = 0
        total_setting_min = 0.0
        prev_key = None

        for key, st in zip(keys, dfx["setting_time"].tolist()):
            if prev_key is None:
                # start – maszyna jest już uzbrojona na pierwszy profil
                prev_key = key
                continue
            
            if key != prev_key:
                st_val = float(st or 0)
                if st_val > 0:
                    setup_count += 1
                    total_setting_min += st_val
                prev_key = key

        total_run_min = 0.0
        run_mode_line = ""

        if choice["mode"] == "speed":
            speed = float(choice["speed_m_per_min"])
            total_run_min = total_m / speed if speed > 0 else 0.0
            run_mode_line = f"Tryb przeliczania: {speed:.2f} m/min\n"
        else:
            pps = int(choice["pieces_per_shift"])
            shifts_needed = (total_pieces / pps) if pps > 0 else 0.0
            total_run_min = shifts_needed * 8.0 * 60.0
            run_mode_line = f"Tryb przeliczania: {pps} szt./zmianę\n"

        total_min = total_setting_min + total_run_min
        shifts = (total_min / 60.0) / 8.0
        rounded_shifts = round_shifts_custom(shifts)

        calendar_mode = choice.get("calendar", "workdays")
        include_weekends = (calendar_mode == "all") 
        start_shift = int(choice.get("start_shift", 1))

        start_mode = choice.get("start_mode", "today")
        start_date_str = choice.get("start_date", date.today().isoformat())
        start_d = date.today() if start_mode != "date" else datetime.strptime(start_date_str, "%Y-%m-%d").date()

        end_d, end_s = add_shifts(
            start_date=start_d,
            start_shift=start_shift,
            shifts_count=rounded_shifts,
            work_saturday=include_weekends,   
            work_sunday=include_weekends    
        )

        # (reszta metody _calculate_confirmation_result pozostaje bez zmian, podmieniasz tylko return na dole)
        return {
            "title": "POTWIERDZENIE TERMINU ZLECENIA",
            "machine": workplace,
            "order": order_id,
            "details": [
                ("Zmiany (8h)", f"{shifts:.2f} → {rounded_shifts}"),
                ("Tryb przeliczania", run_mode_line.replace('Tryb przeliczania:', '').strip()),
                ("Start liczenia", f"{pl_weekday_name(start_d)} ({start_d.isoformat()}) zmiana {start_shift}")
            ],
            "end": f"{pl_weekday_name(end_d)} (zmiana {end_s}) ({end_d.strftime('%d.%m.%Y')})"
        }