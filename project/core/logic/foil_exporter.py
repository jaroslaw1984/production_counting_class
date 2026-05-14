import pandas as pd
import json
import threading
import traceback
import re
from pathlib import Path
from datetime import datetime, date
from project.config.db_loader import fetch_bom_for_articles, set_foil_report_queued
from project.config.paths import FOIL_REPORTS_PATH

class FoilExporter:
    def __init__(self, state, view):
        """
        Inicjalizacja klasy eksportującej.
        Pobiera 'state' (dla danych) i 'view' (do komunikacji z użytkownikiem).
        """
        self.state = state
        self.view = view

    # --- główna metoda wywoływana z kontrolera, która zarządza całym procesem eksportu ---
    def process_export(self):
        try:
            # 1. Pobieramy dane planu i robimy NIEZALEŻNĄ kopię, aby nie psuć widoku w GUI
            df_plan_raw = getattr(self.state, "last_cut_plan_df", None)
            if df_plan_raw is None:
                df_plan_raw = self.state.smart_plan_df

            if df_plan_raw is None or df_plan_raw.empty:
                self.view.show_error("Brak danych", "Nie znaleziono planu produkcji. Wygeneruj najpierw raport.")
                return

            df_plan = df_plan_raw.copy()

            # 2. Ustalamy nazwę maszyny
            machine_name = "Nieznana_Maszyna"
            if self.state.last_report_data and "machine" in self.state.last_report_data:
                machine_name = self.state.last_report_data["machine"]
            elif "workplace" in df_plan.columns and not df_plan["workplace"].dropna().empty:
                machine_name = str(df_plan["workplace"].iloc[0]).strip()

            # 3. Normalizacja Artykułów (usuwanie .0 i białych znaków)
            profile_col = "profile_full" if "profile_full" in df_plan.columns else "profile"
            if profile_col not in df_plan.columns:
                raise ValueError(f"Brak kolumny '{profile_col}' w planie.")
            
            df_plan[profile_col] = df_plan[profile_col].astype("string").str.strip().str.replace(r"\.0$", "", regex=True)
            matnr_list = df_plan[profile_col].dropna().unique().tolist()

            # 4. Sprawdzenie czy plik już istnieje
            out_dir = Path(FOIL_REPORTS_PATH)
            safe_machine_name = str(machine_name).replace("/", "-").replace("\\", "-")
            today_str = date.today().strftime("%Y-%m-%d")
            file_path = out_dir / f"{safe_machine_name}_{today_str}.json"
            
            if file_path.exists():
                should_overwrite = self.view.show_yes_no(
                    "Raport już istnieje",
                    f"Raport dla maszyny {machine_name} na dzień {today_str} już istnieje.\n\nCzy chcesz go zastąpić?"
                )
                if not should_overwrite:
                    return 

            # 5. Uruchomienie zadania w tle
            self.view.show_progress_popup("Generowanie raportu folii...")
            threading.Thread(target=lambda: self._background_task(df_plan, matnr_list, machine_name, profile_col), daemon=True).start()

        except Exception as e:
            self.view.show_error("Błąd przygotowania eksportu", str(e))

    # --- poniżej znajdują się metody pomocnicze, które wykonują główną logikę eksportu w osobnym wątku, aby nie blokować GUI ---
    def _background_task(self, df_plan, matnr_list, machine_name, profile_col):
        """Logika wykonywana w osobnym wątku."""
        try:
            self.view.root.after(0, lambda: self.view.update_progress_popup(10, "Pobieranie BOM z bazy Kronos..."))
            
            bom_df = fetch_bom_for_articles(matnr_list)
            if bom_df.empty:
                raise ValueError("Baza danych nie zwróciła struktury BOM dla tych artykułów.")

            self.view.root.after(0, lambda: self.view.update_progress_popup(30, "Przetwarzanie pozycji planu..."))

            # Agregacja
            def progress_callback(current, total):
                percentage = 30 + int((current / total) * 60)
                self.view.root.after(0, lambda: self.view.update_progress_popup(percentage, f"Analiza: {current}/{total}"))

            # Odbieramy dane raportu ORAZ listę brakujących BOM-ów
            report_data, missing_boms = self._aggregate_foil_requirements(df_plan, bom_df, profile_col, progress_callback)
            
            # Zapis do JSON
            success = self._save_json_payload(machine_name, report_data)
            
            if success:
                msg = f"Raport dla {machine_name} został wyeksportowany."
                
                # --- DOCZEPIANIE OSTRZEŻENIA DO KOMUNIKATU ---
                if missing_boms:
                    missing_boms.sort() # Sortujemy alfabetycznie dla ładnego wyglądu
                    missing_str = "\n- ".join(missing_boms)
                    msg += f"\n\nUwaga! Poniższe zlecenia pominięto z powodu braku folii (BOM) w bazie:\n- {missing_str}"
                # ---------------------------------------------
                
                self.view.root.after(0, lambda: self.view.show_completion_in_popup(msg))
            else:
                self.view.root.after(0, self.view.hide_progress_popup)

        except Exception as e:
            traceback.print_exc()
            self.view.root.after(0, self.view.hide_progress_popup)
            self.view.root.after(0, lambda err=str(e): self.view.show_error("Błąd generowania raportu", err))

    # --- poniżej znajdują się metody, które wykonują konkretne kroki: agregacja danych, łączenie pozycji, ekstrakcja szerokości, zapisywanie do JSON ---
    def _aggregate_foil_requirements(self, df_plan, bom_df, profile_col, progress_callback) -> tuple[dict, list]:
        """Agreguje dane biorąc docelową wartość 1:1 i zwraca też listę brakujących BOM-ów."""
        report_data = {'outer_side': [], 'inner_side': [], 'protective': {}}
        missing_boms = set() # Używamy zbioru (set), żeby artykuły się nie dublowały
        total_rows = len(df_plan)

        for i, (_, row) in enumerate(df_plan.iterrows()):
            matnr = str(row[profile_col]).strip()
            
            # Bierzemy sztywną wartość docelową
            meters = float(row.get("target_value_p", 0.0))
            
            if meters <= 0:
                if progress_callback: progress_callback(i + 1, total_rows)
                continue
                
            requirements = bom_df[bom_df['MATNR'] == matnr]
            
            # --- WYŁAPYWANIE BRAKÓW W KRONOSIE ---
            if requirements.empty:
                missing_boms.add(matnr)
            # ------------------------------------

            for _, bom_row in requirements.iterrows():
                posnr = str(bom_row['POSNR']).strip()
                idnrk = str(bom_row['IDNRK']).strip()
                _, width = self._extract_width_and_type(idnrk)
                
                if posnr in ['0050', '0060']:
                    report_data['protective'][idnrk] = report_data['protective'].get(idnrk, 0.0) + meters
                elif posnr == '0030':
                    self._add_to_list(report_data['outer_side'], idnrk, width, meters, matnr)
                elif posnr == '0020':
                    self._add_to_list(report_data['inner_side'], idnrk, width, meters, matnr)
            
            if progress_callback and (i % 5 == 0 or i == total_rows - 1):
                progress_callback(i + 1, total_rows)
                        
        return report_data, list(missing_boms) # Zwracamy dwie rzeczy!

    # --- metoda pomocnicza do łączenia pozycji, jeśli mają ten sam artykuł i geometrię (np. dwie pozycje z tym samym idnrk i geometry będą zsumowane w metrach) ---
    def _add_to_list(self, target_list, idnrk, width, meters, geometry):
        """Łączy metry jeśli ten sam artykuł i folia występują obok siebie."""
        if target_list and target_list[-1]['idnrk'] == idnrk and target_list[-1]['geometry'] == geometry:
            target_list[-1]['meters'] += meters
        else:
            target_list.append({
                'idnrk': idnrk, 'width': width, 'meters': meters, 'geometry': geometry
            })

    # --- metoda pomocnicza do ekstrakcji szerokości i typu folii z nazwy artykułu (idnrk) ---
    def _extract_width_and_type(self, idnrk: str):
        idnrk = str(idnrk).strip()
        parts = idnrk.split('.')
        prefix = parts[0]
        try:
            width = int(parts[-1])
        except:
            width = 0
        return prefix, width

    # --- metoda pomocnicza do zapisywania gotowego słownika do pliku .json ---
    def _save_json_payload(self, machine_name, report_data) -> bool:
        """Zapisuje gotowy słownik do pliku .json."""
        out_dir = Path(FOIL_REPORTS_PATH)
        out_dir.mkdir(parents=True, exist_ok=True)
        
        safe_name = str(machine_name).replace("/", "-").replace("\\", "-")
        file_path = out_dir / f"{safe_name}_{date.today().strftime('%Y-%m-%d')}.json"
        
        payload = {
            "machine": machine_name,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "data": report_data
        }
        
        file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=4), encoding="utf-8")
        
        try:
            set_foil_report_queued(machine_name)
        except:
            pass
        return True