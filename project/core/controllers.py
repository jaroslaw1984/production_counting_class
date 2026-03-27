from project.config.workplace_config_provider import merge_db_and_csv_config
from project.config.db_loader import fetch_available_machines
from project.config.count_per_loader import update_count_by_shift
from project.config.paths import MACHINE_CONFIG_PATH
from project.config.aliases import ORDER_ALIASES, GRUNDPROFIL_ALIASES, ARTICLE_ALIASES, GOOD_PRODUKTION_ALIASES
from project.config.db_loader import fetch_sap_basic_profiles, fetch_available_machines
from pathlib import Path
import pandas as pd
import traceback

class MainController:
    def __init__(self, state, view):
        self.state = state
        self.view = view
        
    def handle_load_machines(self):
        # Testowanie połączenia
        print("Kontroler odebrał sygnał z GUI: Rozpoczynam wczytywanie maszyn z DB/CSV...")
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
            
    # --- To ona odbiera kliknięcie "Przelicz" z popupu ---
    def on_machines_selected(self, selected_machines, pps_by_machine, save_snapshot, changes, should_save_config):
        print(f"Kontroler odebrał z popupu: Wybrano maszyn {len(selected_machines)}.")
        
        # Jeśli użytkownik kliknął "TAK" na pytanie o zapis zmian
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
            
            # Zapis do DB
            if self.state.machine_cfg_source in ("db", "db+csv"):
                try:
                    for m, _, new_val in changes:
                        update_count_by_shift(m, new_val)
                except Exception as e:
                    self.view.show_warning("Uwaga", f"Zapisano do pliku CSV, ale błąd zapisu DB:\n{e}")
            
            # Odświeżenie stanu
            df_cfg, source, missing = merge_db_and_csv_config(sync_missing_to_db=False)
            self.state.machine_cfg = df_cfg
            self.state.machine_cfg_source = source

        # TUTAJ w przyszłości wywołamy logikę przeliczania (calculate_from_db)
        print("Kontroler: Zapisano konfigurację. Czekam na logikę obliczeń!")
        
    def handle_generate_report(self):
            print("Kontroler: Rozpoczynam generowanie raportu...")
            
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
            
    def on_report_params_selected(self, params: dict):
            """Ta funkcja odpali się, gdy użytkownik kliknie OK w popupie"""
            print(f"Kontroler otrzymał parametry od użytkownika: {params}")
            
            linia_value = params["linia"]
            start_order_id = params["start_order_id"]
            day_value = params["day"]
            
            # --- 1. Cięcie Hydry (OBOWIĄZKOWE) ---
            try:
                df_group = self._cut_from_order(self.state.df_hydra, start_order_id)
                traceback.print_exc()
            except Exception as e:
                # Jeśli nie ma zlecenia w Hydrze, przerywamy wszystko
                self.view.show_error("Błąd cięcia danych (Hydra)", str(e))
                return

            # --- 2. Cięcie Smart Planu (OPCJONALNE / SMART MATCHING) ---
            df_cut_plan = None
            if self.state.smart_plan_df is not None:
                try:
                    df_cut_plan = self._cut_from_order(self.state.smart_plan_df, start_order_id)
                except Exception as e:
                    # Jeśli plan nie ma tego zlecenia, tylko ostrzegamy, nie przerywamy!
                    print(f"Uwaga: Brak zlecenia w Smart Planie. Wyłączam Smart Matching.")
                    self.view.show_warning(
                        "Ostrzeżenie Smart Plan", 
                        f"Plan nie pasuje do startowego zlecenia.\nRaport wygeneruje się bez inteligentnego dopasowania (Fallback).\n\nSzczegóły: {str(e)}"
                    )
                    df_cut_plan = None # Ustawiamy na None, żeby program użył trybu awaryjnego

            # --- 3. Pobieranie SAP i budowa bloków ---
            try:
                blocks = self._build_blocks(df_group)
                
                df_sap = fetch_sap_basic_profiles(linia=linia_value, day=day_value)
                if df_sap is None or df_sap.empty:
                    raise ValueError(f"Nie znaleziono danych SAP dla linii: {linia_value} w dniu: {day_value}")
                
                print(f"Zbudowano bloków z Hydry: {len(blocks)}")
                print(f"Pobrano wierszy z SAP: {len(df_sap)}")    
                
            except Exception as e:
                self.view.show_error("Błąd przetwarzania raportu", str(e))
                return
            
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
            
            # Tymczasowy test w konsoli:
            print("Kontroler: Plik załadowany pomyślnie!")
            print(f"Ilość wierszy kolejki Hydry: {len(df_hydra_queue) if df_hydra_queue is not None else 0}")
            print(f"Ilość wierszy Smart Planu: {len(df_smart_plan ) if df_smart_plan is not None else 0}")
        except Exception as e:
            self.view.show_error("Błąd wczytywania pliku", str(e))   
    
    def _extract_hydra_queue(self, df: pd.DataFrame) -> pd.DataFrame:
            """Podwykonawca 1: Wyciąga tylko kolejność zleceń i profili z Hydry."""
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
    
    def _build_blocks(self, df: pd.DataFrame) -> list[dict]:
        """Grupuje ciągłe zlecenia o tym samym grundprofil i side w bloki."""
        tmp = df.copy()
        tmp["grundprofil"] = tmp["grundprofil"].astype("string").str.strip()
        tmp["side"] = tmp["side"].astype("string").str.strip().str.zfill(4)
        
        # Opcjonalna normalizacja zer wiodących na potrzeby grupowania
        mask = tmp["order_id"].str.fullmatch(r"\d+").fillna(False) & (tmp["order_id"].str.len() < 12)
        tmp.loc[mask, "order_id"] = tmp.loc[mask, "order_id"].str.zfill(12)

        blocks: list[dict] = []
        prev = None
        start = 0
        keys = list(zip(tmp["grundprofil"].tolist(), tmp["side"].tolist()))

        for i, key in enumerate(keys):
            if key != prev:
                if prev is not None:
                    b = tmp.iloc[start:i]
                    blocks.append({
                        "gp": prev[0],
                        "side": prev[1],
                        "order_ids": set(b["order_id"].tolist()),
                        "start_i": start,
                        "end_i": i - 1,
                    })
                prev = key
                start = i

        if prev is not None and len(tmp) > 0:
            b = tmp.iloc[start:]
            blocks.append({
                "gp": prev[0],
                "side": prev[1],
                "order_ids": set(b["order_id"].tolist()),
                "start_i": start,
                "end_i": len(tmp) - 1,
            })
            
        return blocks