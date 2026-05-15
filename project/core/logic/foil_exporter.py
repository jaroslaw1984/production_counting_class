import pandas as pd
import json
import threading
import traceback
import re
from pathlib import Path
from datetime import datetime, date
from project.config.db_loader import fetch_bom_for_articles, set_foil_report_queued
from project.config.paths import FOIL_REPORTS_PATH, DOUBLE_SIDED_MACHINES_CONFIG

class FoilExporter:
    def __init__(self, state, view):
        self.state = state
        self.view = view

    def _is_double_sided(self, machine_name: str) -> bool:
        """Sprawdza w pliku konfiguracyjnym, czy maszyna jest dwustronna (kombajn)."""
        config_path = Path(DOUBLE_SIDED_MACHINES_CONFIG)
        if not config_path.exists():
            return False
        
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                machines_list = json.load(f)
            return any(str(m).strip() in machine_name for m in machines_list)
        except Exception as e:
            print(f"Błąd odczytu konfiguracji maszyn obustronnych: {e}")
            return False

    def process_export(self):
        try:
            df_plan_raw = getattr(self.state, "last_cut_plan_df", None)
            if df_plan_raw is None:
                df_plan_raw = self.state.smart_plan_df

            if df_plan_raw is None or df_plan_raw.empty:
                self.view.show_error("Brak danych", "Nie znaleziono planu produkcji.")
                return

            df_plan = df_plan_raw.copy()

            machine_name = "Nieznana_Maszyna"
            if self.state.last_report_data and "machine" in self.state.last_report_data:
                machine_name = self.state.last_report_data["machine"]
            elif "workplace" in df_plan.columns and not df_plan["workplace"].dropna().empty:
                machine_name = str(df_plan["workplace"].iloc[0]).strip()

            # Zmieniona nazwa zmiennej na bardziej czytelną
            is_double_sided_machine = self._is_double_sided(machine_name)

            profile_col = "profile_full" if "profile_full" in df_plan.columns else "profile"
            df_plan[profile_col] = df_plan[profile_col].astype("string").str.strip().str.replace(r"\.0$", "", regex=True)
            matnr_list = df_plan[profile_col].dropna().unique().tolist()

            out_dir = Path(FOIL_REPORTS_PATH)
            safe_name = str(machine_name).replace("/", "-").replace("\\", "-")
            file_path = out_dir / f"{safe_name}_{date.today().strftime('%Y-%m-%d')}.json"
            
            if file_path.exists():
                if not self.view.show_yes_no("Raport istnieje", "Czy zastąpić istniejący raport?"):
                    return 

            self.view.show_progress_popup("Generowanie raportu folii...")
            threading.Thread(target=lambda: self._background_task(df_plan, matnr_list, machine_name, profile_col, is_double_sided_machine), daemon=True).start()

        except Exception as e:
            self.view.show_error("Błąd", str(e))

    def _background_task(self, df_plan, matnr_list, machine_name, profile_col, is_double_sided_machine):
        try:
            self.view.root.after(0, lambda: self.view.update_progress_popup(10, "Pobieranie BOM..."))
            bom_df = fetch_bom_for_articles(matnr_list)
            
            self.view.root.after(0, lambda: self.view.update_progress_popup(30, "Agregowanie danych..."))
            
            def progress_cb(current, total):
                p = 30 + int((current / total) * 60)
                self.view.root.after(0, lambda: self.view.update_progress_popup(p, f"Analiza: {current}/{total}"))

            report_data, missing_boms = self._aggregate_foil_requirements(df_plan, bom_df, profile_col, is_double_sided_machine, progress_cb)
            
            success = self._save_json_payload(machine_name, report_data, is_double_sided_machine)
            
            if success:
                msg = f"Raport dla {machine_name} gotowy."
                if missing_boms:
                    msg += f"\n\nBrak BOM dla:\n- " + "\n- ".join(sorted(missing_boms))
                self.view.root.after(0, lambda: self.view.show_completion_in_popup(msg))
            else:
                self.view.root.after(0, self.view.hide_progress_popup)

        except Exception as e:
            traceback.print_exc()
            self.view.root.after(0, self.view.hide_progress_popup)
            self.view.root.after(0, lambda err=str(e): self.view.show_error("Błąd", err))

    def _aggregate_foil_requirements(self, df_plan, bom_df, profile_col, is_double_sided_machine, progress_callback) -> tuple[dict, list]:
        report_data = {'outer_side': [], 'inner_side': [], 'combined_side': [], 'protective': {}}
        missing_boms = set()
        total_rows = len(df_plan)

        for i, (_, row) in enumerate(df_plan.iterrows()):
            matnr = str(row[profile_col]).strip()
            meters = float(row.get("target_value_p", 0.0))
            
            if meters <= 0:
                if progress_callback: progress_callback(i + 1, total_rows)
                continue
                
            requirements = bom_df[bom_df['MATNR'] == matnr]
            if requirements.empty:
                missing_boms.add(matnr)

            if is_double_sided_machine:
                for side_pos in ['0030', '0020']:
                    side_req = requirements[requirements['POSNR'].astype(str).str.strip() == side_pos]
                    for _, bom_row in side_req.iterrows():
                        idnrk = str(bom_row['IDNRK']).strip()
                        _, width = self._extract_width_and_type(idnrk)
                        self._add_to_list(report_data['combined_side'], idnrk, width, meters, matnr, i)
            else:
                for _, bom_row in requirements.iterrows():
                    posnr = str(bom_row['POSNR']).strip()
                    idnrk = str(bom_row['IDNRK']).strip()
                    _, width = self._extract_width_and_type(idnrk)
                    
                    if posnr == '0030':
                        self._add_to_list(report_data['outer_side'], idnrk, width, meters, matnr, i)
                    elif posnr == '0020':
                        self._add_to_list(report_data['inner_side'], idnrk, width, meters, matnr, i)

            prot_req = requirements[requirements['POSNR'].isin(['0050', '0060'])]
            for _, bom_row in prot_req.iterrows():
                idnrk = str(bom_row['IDNRK']).strip()
                report_data['protective'][idnrk] = report_data['protective'].get(idnrk, 0.0) + meters

            if progress_callback and (i % 5 == 0 or i == total_rows - 1):
                progress_callback(i + 1, total_rows)
                        
        return report_data, list(missing_boms)

    def _add_to_list(self, target_list, idnrk, width, meters, geometry, order_index):
        if target_list and target_list[-1]['idnrk'] == idnrk and target_list[-1]['geometry'] == geometry:
            target_list[-1]['meters'] += meters
        else:
            target_list.append({
                'idnrk': idnrk, 'width': width, 'meters': meters, 'geometry': geometry, 'order_index': order_index
            })

    def _extract_width_and_type(self, idnrk: str):
        idnrk = str(idnrk).strip()
        parts = idnrk.split('.')
        try:
            width = int(parts[-1])
        except:
            width = 0
        return parts[0], width

    def _save_json_payload(self, machine_name, report_data, is_double_sided_machine) -> bool:
        out_dir = Path(FOIL_REPORTS_PATH)
        out_dir.mkdir(parents=True, exist_ok=True)
        
        safe_name = str(machine_name).replace("/", "-").replace("\\", "-")
        file_path = out_dir / f"{safe_name}_{date.today().strftime('%Y-%m-%d')}.json"
        
        payload = {
            "machine": machine_name,
            "is_double_sided": is_double_sided_machine,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "data": report_data
        }
        
        file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=4), encoding="utf-8")
        
        # --- ZDJĘCIE KNEBLA Z BŁĘDÓW BAZY DANYCH ---
        try:
            set_foil_report_queued(machine_name)
            print(f"[SIGNAL KRONOS] SUKCES: Wysłano sygnał gotowości dla: {machine_name}")
        except Exception as e:
            print(f"[SIGNAL KRONOS] BŁĄD KRYTYCZNY: Nie udało się wysłać sygnału do bazy!")
            print(f"Szczegóły błędu: {e}")
            
        return True