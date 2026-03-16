from project.core.app_state import AppState
from project.GUI.main_windows import MainWindow
from project.core.controllers import MainController

def run_app():
    state = AppState()
    main_window = MainWindow(state)
    
    # Tworzymy kontroler i przekazujemy mu stan i widok
    controller = MainController(state, main_window)
    
    # Podpinamy kontroler pod GUI
    main_window.set_controller(controller)
    
    main_window.run()
    
if __name__ == "__main__":
    run_app()