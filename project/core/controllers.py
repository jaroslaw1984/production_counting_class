from project.config.workplace_config_provider import merge_db_and_csv_config
from project.config.db_loader import fetch_available_machines

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
            self.view.show_machine_select_popup(machines)
            
        except Exception as e:
            # --- Błąd (np. brak VPN / sterownika) -> polecenie dla widoku, aby wyświetlił błąd ---
            error_msg = f"Brak sterownika ODBC / brak dostępu do sieci firmowej.\n\nMożesz użyć trybu: Wczytaj plik (Excel)\n\nSzczegóły błędu:\n{str(e)}"
            self.view.show_error("Błąd połączenia:", error_msg)