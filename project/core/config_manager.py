import csv
import json
from pathlib import Path
from typing import List, Dict, cast

# Zaktualizowane importy - korzystamy z istniejących funkcji z Twoich modułów
from project.config.count_per_loader import (
    save_profile_to_db, 
    delete_profile_from_db, 
    fetch_profiles_config
)
from project.config.workplace_config_provider import _normalize_profiles_db_df

class ConfigDataManager:
    def __init__(self, ds_machines_path: str | Path, machines_csv_path: str | Path, profiles_csv_path: str | Path):
        self.ds_machines_path = Path(ds_machines_path)
        self.machines_csv_path = Path(machines_csv_path)
        self.profiles_csv_path = Path(profiles_csv_path)
        self.delimiter = ';'

    # ==========================================
    # OBSŁUGA MASZYN OBUSTRONNYCH (JSON)
    # ==========================================
    def get_ds_machines(self) -> List[str]:
        if not self.ds_machines_path.exists():
            return []
        try:
            with open(self.ds_machines_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return []

    def _save_ds_machines(self, machines: List[str]) -> bool:
        try:
            with open(self.ds_machines_path, 'w', encoding='utf-8') as f:
                json.dump(machines, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Błąd zapisu JSON: {e}")
            return False

    def add_ds_machine(self, machine_name: str) -> bool:
        machines = self.get_ds_machines()
        if machine_name not in machines:
            machines.append(machine_name)
            return self._save_ds_machines(machines)
        return False

    def delete_ds_machine(self, machine_name: str) -> bool:
        machines = self.get_ds_machines()
        if machine_name in machines:
            machines.remove(machine_name)
            return self._save_ds_machines(machines)
        return False

    # ==========================================
    # METODY POMOCNICZE DLA CSV
    # ==========================================
    def _read_csv(self, file_path: Path) -> List[Dict[str, str]]:
        if not file_path.exists():
            return []
        # Zmiana kodowania na 'utf-8-sig' usuwa problem z niewidocznym znakiem BOM z Excela
        with open(file_path, 'r', encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f, delimiter=self.delimiter)
            return list(reader)

    def _write_csv(self, file_path: Path, fieldnames: List[str], data: List[Dict[str, str]]) -> bool:
        try:
            # Tutaj również używamy 'utf-8-sig', aby zachować pełną kompatybilność z Excelem
            with open(file_path, 'w', encoding='utf-8-sig', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=self.delimiter)
                writer.writeheader()
                writer.writerows(data)
            return True
        except Exception as e:
            print(f"Błąd zapisu CSV ({file_path.name}): {e}")
            return False

    # ==========================================
    # OBSŁUGA MASZYN I STANOWISK (CSV)
    # ==========================================
    def get_machines(self) -> List[Dict[str, str]]:
        return self._read_csv(self.machines_csv_path)

    def save_machine(self, workplace: str, speed: str, count: str) -> bool:
        machines = self.get_machines()
        fieldnames = ['workplace', 'speed_m_per_min', 'count_by_shift']
        
        updated = False
        for m in machines:
            if m['workplace'] == workplace:
                m['speed_m_per_min'] = speed
                m['count_by_shift'] = count
                updated = True
                break
        
        if not updated:
            machines.append({'workplace': workplace, 'speed_m_per_min': speed, 'count_by_shift': count})
            
        return self._write_csv(self.machines_csv_path, fieldnames, machines)

    def delete_machine(self, workplace: str) -> bool:
        machines = self.get_machines()
        fieldnames = ['workplace', 'speed_m_per_min', 'count_by_shift']
        new_machines = [m for m in machines if m['workplace'] != workplace]
        
        if len(machines) == len(new_machines):
            return False  # Nic nie usunięto
        return self._write_csv(self.machines_csv_path, fieldnames, new_machines)

    # ==========================================
    # OBSŁUGA GEOMETRII / PROFILI (TYLKO DB)
    # ==========================================
    def get_profiles(self) -> List[Dict[str, str]]:
        try:
            # 1. Pobranie danych bezpośrednio z bazy
            df = fetch_profiles_config()
            
            if df is None or df.empty:
                return []
                
            # 2. Użycie Twojej istniejącej funkcji do normalizacji (czyszczenie spacji, int dla czasu)
            df = _normalize_profiles_db_df(df)
            
            if 'setting_time' not in df.columns:
                print("BŁĄD: Brak kolumny 'setting_time' w pobranych danych SQL!")
                return []
                
            # 3. Konwersja na str, aby utrzymać kompatybilność z polami tekstowymi CustomTkinter
            df['setting_time'] = df['setting_time'].astype(str)
            
            # Zamiana DataFrame na listę słowników dla GUI
            return cast(List[Dict[str, str]], df.to_dict('records'))
            
        except Exception as e:
            print(f"KRYTYCZNY BŁĄD podczas budowania listy profili z DB: {e}")
            import traceback
            traceback.print_exc()
            return []

    def save_profile(self, profile: str, side: str, setting_time: str) -> bool:
        # Zapis tylko do bazy SQL jako SSOT (Single Source of Truth)
        db_success = save_profile_to_db(profile, side, int(setting_time))
        
        if not db_success:
            print(f"BŁĄD: Nie udało się zapisać w bazie nowej geometrii ({profile}).")
            
        return db_success

    def delete_profile(self, profile: str, side: str) -> bool:
        # Normalizacja danych z GUI
        profile_clean = str(profile).strip()
        side_clean = str(side).strip().zfill(4)
        
        # Usunięcie tylko z bazy SQL
        db_success = delete_profile_from_db(profile_clean, side_clean)
        
        if not db_success:
             print(f"UWAGA: Nie usunięto z bazy (geometria {profile_clean} może nie istnieć lub brak połączenia).")
             
        return db_success