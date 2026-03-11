from project.core.app_state import AppState
from project.GUI.main_windows import MainWindow

def run_app():
    state = AppState()
    main_window = MainWindow(state)
    main_window.run()
    
if __name__ == "__main__":
    run_app()