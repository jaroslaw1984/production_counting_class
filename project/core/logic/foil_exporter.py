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
            
            # --- ZABEZPIECZENIE PRZED "Maszyna 1" w "Maszyna 11" ---
            # Używamy re.search z tzw. "negative lookahead" (?!\d).
            # Szukamy nazwy, ale sprawdzamy, czy zaraz za nią nie stoi inna cyfra.
            for m in machines_list:
                pattern = re.escape(str(m).strip()) + r"(?!\d)"
                if re.search(pattern, machine_name):
                    return True
            return False
            
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
            
            # --- ZABÓJCA "DUCHÓW" Z BAZY KRONOS ---
            if not bom_df.empty:
                bom_df['MATNR'] = bom_df['MATNR'].astype("string").str.strip()
                bom_df['POSNR'] = bom_df['POSNR'].astype("string").str.strip()
                bom_df['IDNRK'] = bom_df['IDNRK'].astype("string").str.strip()
                # Usuwamy zduplikowane wiersze dla tego samego artykułu i pozycji BOM
                bom_df = bom_df.drop_duplicates(subset=['MATNR', 'POSNR', 'IDNRK'])
            # --------------------------------------

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
        report_data = {'production_sequence': [], 'combined_side': [], 'protective': {}}
        missing_boms = set()

        grouped_plan = []
        for i, (_, row) in enumerate(df_plan.iterrows()):
            matnr = str(row[profile_col]).strip()
            meters = float(row.get("target_value_p", 0.0))
            side = str(row.get("side", "")).strip().replace(".0", "").zfill(4)

            if meters <= 0:
                continue
                
            if grouped_plan and grouped_plan[-1]['matnr'] == matnr and grouped_plan[-1]['side'] == side:
                grouped_plan[-1]['meters'] += meters
            else:
                grouped_plan.append({'matnr': matnr, 'meters': meters, 'side': side, 'order_index': i})

        total_groups = len(grouped_plan)
        
        # --- POPRAWIONE MAPOWANIE HYDRA -> KRONOS ---
        op_to_posnr = {
            '0021': ['0030'],            # Zewnętrzna
            '0022': ['0020'],            # Wewnętrzna
            '0023': ['0070'],            # Górna
            '0020': ['0030', '0020']     # Obustronnie (Kombajn)
        }
        
        posnr_desc = {
            '0030': 'Zewn.',
            '0020': 'Wewn.',
            '0070': 'Górna'
        }

        for i, item in enumerate(grouped_plan):
            matnr = item['matnr']
            meters = item['meters']
            op_side = item['side']
            order_idx = item['order_index']
            
            requirements = bom_df[bom_df['MATNR'] == matnr]
            if requirements.empty:
                missing_boms.add(matnr)

            if is_double_sided_machine:
                # --- TRYB KOMBAJNU (Wszystko razem) ---
                for side_pos in ['0030', '0020', '0070']: 
                    side_req = requirements[requirements['POSNR'] == side_pos]
                    for _, bom_row in side_req.iterrows():
                        idnrk = str(bom_row['IDNRK'])
                        _, width = self._extract_width_and_type(idnrk)
                        
                        report_data['combined_side'].append({
                            'idnrk': idnrk, 'width': width, 'meters': meters, 'geometry': matnr, 'order_index': order_idx
                        })
            else:
                # --- TRYB PRZEPLATANY DLA RESZTY MASZYN ---
                target_posnrs = op_to_posnr.get(op_side, ['0030', '0020', '0070'])
                for posnr in target_posnrs:
                    side_req = requirements[requirements['POSNR'] == posnr]
                    for _, bom_row in side_req.iterrows():
                        idnrk = str(bom_row['IDNRK'])
                        _, width = self._extract_width_and_type(idnrk)
                        
                        report_data['production_sequence'].append({
                            'idnrk': idnrk, 
                            'width': width, 
                            'meters': meters, 
                            'geometry': matnr, 
                            'order_index': order_idx,
                            'side_desc': posnr_desc.get(posnr, '')
                        })

            prot_req = requirements[requirements['POSNR'].isin(['0050', '0060', '0090'])]
            for _, bom_row in prot_req.iterrows():
                idnrk = str(bom_row['IDNRK'])
                report_data['protective'][idnrk] = report_data['protective'].get(idnrk, 0.0) + meters

            if progress_callback and (i % 5 == 0 or i == total_groups - 1):
                progress_callback(i + 1, total_groups)
                        
        return report_data, list(missing_boms)

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
        
        # Ustawiamy domyślny format od razu z kropkami
        snapshot_date_str = date.today().strftime('%d.%m.%Y')
        try:
            import os
            # Poprawiona ścieżka - APPDATA zawiera już w sobie "Roaming"
            snap_path = Path(os.getenv("APPDATA") or Path.home()) / "ProductionCounter" / "production_snapshot.json"
            if snap_path.exists():
                with open(snap_path, "r", encoding="utf-8") as f:
                    snap_data = json.load(f)
                    if "snapshot_date" in snap_data:
                        parsed_date = datetime.strptime(snap_data["snapshot_date"], "%Y-%m-%d")
                        snapshot_date_str = parsed_date.strftime("%d.%m.%Y")
        except Exception as e:
            print(f"Nie udało się odczytać daty snapshota dla raportu folii: {e}")
        
        # --- KLUCZOWA ZMIANA: Dodajemy datę do wnętrza raportu, aby Word ją zobaczył ---
        report_data["snapshot_date"] = snapshot_date_str
        
        payload = {
            "machine": machine_name,
            "is_double_sided": is_double_sided_machine,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "data": report_data
        }
        
        file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=4), encoding="utf-8")
        
        try:
            set_foil_report_queued(machine_name)
            print(f"[SIGNAL KRONOS] SUKCES: Wysłano sygnał gotowości dla: {machine_name}")
        except Exception as e:
            print(f"[SIGNAL KRONOS] BŁĄD KRYTYCZNY: Nie udało się wysłać sygnału do bazy!")
            print(f"Szczegóły błędu: {e}")
            
        return True