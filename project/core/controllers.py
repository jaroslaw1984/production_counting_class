class MainController:
    def __init__(self, state, view):
        self.state = state
        self.view = view
        
    def handle_load_machines(self):
        # Na razie tylko sprawdzamy, czy "kable" są dobrze podłączone
        print("Kontroler odebrał sygnał z GUI: Rozpoczynam wczytywanie maszyn z DB/CSV...")
        