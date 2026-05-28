import csv
import json
from pathlib import Path
from typing import List, Dict, Optional

class ConfigDataManager:
    """
    Klasa odpowiedzialna za bezpieczny odczyt i zapis konfiguracji
    z plików CSV oraz JSON. Oddziela operacje plikowe od GUI.
    """
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
        with open(file_path, 'r', encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f, delimiter=self.delimiter)
            return list(reader)

    def _write_csv(self, file_path: Path, fieldnames: List[str], data: List[Dict[str, str]]) -> bool:
        try:
            with open(file_path, 'w', encoding='utf-8', newline='') as f:
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
    # OBSŁUGA GEOMETRII / PROFILI (CSV)
    # ==========================================
    def get_profiles(self) -> List[Dict[str, str]]:
        return self._read_csv(self.profiles_csv_path)

    def save_profile(self, profile: str, side: str, setting_time: str) -> bool:
        profiles = self.get_profiles()
        fieldnames = ['profile', 'side', 'setting_time']
        
        updated = False
        for p in profiles:
            if p['profile'] == profile and p['side'] == side:
                p['setting_time'] = setting_time
                updated = True
                break
        
        if not updated:
            profiles.append({'profile': profile, 'side': side, 'setting_time': setting_time})
            
        return self._write_csv(self.profiles_csv_path, fieldnames, profiles)

    def delete_profile(self, profile: str, side: str) -> bool:
        profiles = self.get_profiles()
        fieldnames = ['profile', 'side', 'setting_time']
        # Usuwamy tylko ten wiersz, gdzie zgadza się i profil, i strona
        new_profiles = [p for p in profiles if not (p['profile'] == profile and p['side'] == side)]
        
        if len(profiles) == len(new_profiles):
            return False
        return self._write_csv(self.profiles_csv_path, fieldnames, new_profiles)