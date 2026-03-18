from project.config.workplace_config_provider import merge_db_and_csv_config
from project.config.db_loader import fetch_available_machines
from project.config.count_per_loader import update_count_by_shift
from project.GUI.main_windows import MACHINE_CONFIG_PATH
import pandas as pd

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