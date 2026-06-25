import csv
import json
from pathlib import Path
from typing import List, Dict, cast
from project.config.workplace_config_provider import merge_db_and_csv_profiles
from project.config.count_per_loader import save_profile_to_db, delete_profile_from_db

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

    # ==========================================\
    # OBSŁUGA GEOMETRII / PROFILI (DB + CSV)
    # ==========================================\
    def get_profiles(self) -> List[Dict[str, str]]:
        try:
            df, source = merge_db_and_csv_profiles()
            
            # Dodatkowe zabezpieczenie upewniające się, że kolumna istnieje przed rzutowaniem
            if 'setting_time' not in df.columns:
                print("BŁĄD: Brak kolumny 'setting_time' w pobranych danych!")
                return []
                
            # Konwersja int z powrotem na str, aby utrzymać kompatybilność z obecnym kodem GUI
            df['setting_time'] = df['setting_time'].astype(str)
            
            # Zamiana DataFrame na format jakiego oczekuje GUI
            return cast(List[Dict[str, str]], df.to_dict('records'))
            
        except Exception as e:
            # W razie jakiegokolwiek błędu wypiszemy go, ale zwrócimy pustą listę,
            # dzięki temu GUI CustomTkinter nie zniknie w połowie rysowania.
            print(f"KRYTYCZNY BŁĄD podczas budowania listy profili: {e}")
            import traceback
            traceback.print_exc()
            return []

    def save_profile(self, profile: str, side: str, setting_time: str) -> bool:
        # 1. Zapis do bazy SQL jako głównego źródła
        db_success = save_profile_to_db(profile, side, int(setting_time))
        if not db_success:
            print("Nie udało się zapisać w DB. Dane zostaną zapisane tylko w CSV.")

        # 2. Zapis do pliku CSV (lokalny bufor / fallback)
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
        # Normalizacja danych wysyłanych z GUI
        profile_clean = str(profile).strip()
        side_clean = str(side).strip().zfill(4)
        
        # 1. Usunięcie z bazy SQL
        db_success = delete_profile_from_db(profile_clean, side_clean)
        if not db_success:
             print("UWAGA: Nie usunięto z DB (może nie istnieć lub brak połączenia).")

        # 2. Aktualizacja pliku CSV
        profiles = self.get_profiles()
        fieldnames = ['profile', 'side', 'setting_time']
        
        # Filtrujemy listę używając znormalizowanych wartości
        new_profiles = [
            p for p in profiles 
            if not (str(p['profile']).strip() == profile_clean and str(p['side']).strip().zfill(4) == side_clean)
        ]
        
        # 3. Zapisujemy odświeżoną listę do lokalnego pliku CSV
        self._write_csv(self.profiles_csv_path, fieldnames, new_profiles)
        
        # Zwracamy True, jeśli baza zgłosiła usunięcie ALBO usunęliśmy z lokalnego pliku.
        # Dzięki temu GUI odświeży się prawidłowo, a plik CSV będzie idealnym odbiciem bazy.
        if db_success or len(new_profiles) < len(profiles):
            return True
            
        return False