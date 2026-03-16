import customtkinter as ctk
from project.core.app_state import AppState
from tkinter import messagebox

class MainWindow:
    def __init__(self, state: AppState):
        self.state = state
        
        # --- Konfiguracja wyglądu ---
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("dark-blue")
                
        # --- Root window ---
        self.root = ctk.CTk()
        self.root.title("Policz produkcję")
        self.root.geometry("800x600")
        
        # --- Ustawienia czcionki ---
        self.default_font = ctk.CTkFont(family="Segoe UI", size=14)
       
        # --- Budowa UI ---
        self._configure_layout()
        self._build_left_panel()
        self._build_right_panel()
        
    def set_controller(self, controller):
        self.controller = controller    
    
    # # # # # # # # # # # # # # # # # # # #
    # Budowa lewej części (panel boczny)  #
    # # # # # # # # # # # # # # # # # # # #  
     
    def _build_left_panel(self):
        # --- główny kontener ---
        self.left = ctk.CTkFrame(self.root)
        self.left.grid(row=0, column=0, sticky="ns", padx=5, pady=5)
        self.left.grid_columnconfigure(0, weight=1) # tylko góra-dół
        self.left.grid_rowconfigure(1, weight=1)  # push przyciski do góry
        
        # --- górne przyciski ---
        self.top_frame = ctk.CTkFrame(self.left, fg_color="transparent")
        self.top_frame.grid(row=0, column=0, sticky="ns", pady=(10, 10))
        self.top_frame.grid_columnconfigure(0, weight=1)        
    
        # --- dolne przyciski ---
        self.down_frame = ctk.CTkFrame(self.left, fg_color="transparent")
        self.down_frame.grid(row=2, column=0, sticky="ns", pady=(10, 10))
        self.down_frame.grid_columnconfigure(0, weight=1)
               
        # --- definicja dla górnych przycisków (tekst, handler) ---
        top_buttons = [
            ("Wczytaj maszyny", self.loading_machine_data),
            ("Wczytaj plik", self.on_open_file),
            ("Przelicz produkcję", self.calculate_production),
            ("Generuj raport", self.generate_logistics_report),
            ("Potwierdż termin", self.confirm_order),
            ("Wyczyść", self.clean_text),
        ]
    
        # --- tworzenie przycisków w pętli ---
        for row, (label, handler) in enumerate(top_buttons):
            btn = ctk.CTkButton(
                self.top_frame,
                text=label,
                command=handler,
                font=self.default_font
            )
            btn.grid(row=row, column=0, sticky="ew", padx=10, pady=10)
            
        # --- Ręczna definicja przycisku motywu w dolnym panelu ---
        self.theme_button = ctk.CTkButton(
            self.down_frame,
            text=self._get_theme_button_text(), # Od razu pobiera właściwy tekst
            command=self.change_theme,
            font=self.default_font
        )
        self.theme_button.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
             
        # --- definicja dolnych przycisków (tekst, handler) ---     
        bottom_buttons = [
            ("Pomoc", self.help_btn),
            ("O programie", self.about_btn)  
        ]
        
        # --- tworzenie przycisków dolnych w pętli --- 
        for row, (label, handler) in enumerate(bottom_buttons, start=1):
            btn = ctk.CTkButton(
                self.down_frame,
                text=label,
                command=handler,
                font=self.default_font
            )
            btn.grid(row=row, column=0, sticky="ew", padx=10, pady=10)
    
    # # # # # # # # # # # # # # # # #
    # Budowa prawej części (główna) #
    # # # # # # # # # # # # # # # # #                  

    def _build_right_panel(self):
        # --- Prawa część (rośnie w obie strony ---
        self.right = ctk.CTkFrame(self.root)
        self.right.grid(row=0, column=1, sticky="nsew", padx=10, pady=10) # rośnie w obie strony

        # --- Wnętrze prawego panelu też responsywne ---
        self.right.grid_columnconfigure(0, weight=1)
        self.right.grid_rowconfigure(0, weight=0)  # toolbar
        self.right.grid_rowconfigure(1, weight=1)  # treść (textbox / tabela)        

        self.text = ctk.CTkTextbox(self.right)
        self.text.grid(row=1, column=0, sticky="nsew")
        self.text.configure(state="disabled") 
    
    # --- pobieranie tekstu dla zmiany motywu    
    def _get_theme_button_text(self) -> str:
        return "Jasny motyw" if ctk.get_appearance_mode() == "Dark" else "Ciemny motyw"
    
    # --- zmiana motywu Dark / Light ---
    def change_theme(self):
        if ctk.get_appearance_mode() == "Light":
            ctk.set_appearance_mode("Dark")
        else:
            ctk.set_appearance_mode("Light")
            
        # --- aktualizacja tekstu przycisku ---
        self.theme_button.configure(text=self._get_theme_button_text())
        
    # --- Konfiguracja layoutu root window ---        
    def _configure_layout(self):    
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)
        
    def loading_machine_data(self):
        if hasattr(self, 'controller'):
            self.controller.handle_load_machines()
        
    def on_open_file(self):
        print("Otwieranie pliku...")
        
    def calculate_production(self):
        print("Liczenie produkcji...")
        
    def generate_logistics_report(self):
        print("Generowanie raportu logistycznego...")
        
    def confirm_order(self):
        print("Potwierdzenie raportu...")
        
    def clean_text(self):
        print("Czyszczenie tekstu...")
        
    def help_btn(self):
        print("Pomoc")
        
    def about_btn(self):
        print("O programe")

    def run(self):
        self.root.mainloop()
        
    # # # # # # # # # # # # # # # # # # # # # #
    # Helpery dla kontrolera controllers.py)  #
    # # # # # # # # # # # # # # # # # # # # # #
    
    # --- obsługa błędów ---
    def show_error(self, title: str, message: str):
        messagebox.showerror(title, message)
        
    def show_warning(self, title: str, message: str):
        messagebox.showerror(title, message)
        
    # --- Wyświetlanie w popup listę maszyn ---
    def show_machine_select_popup(self, machines: list[str]):
        # Na razie to tylko test, czy dane poprawnie dotarły z bazy
        print(f"Widok: Otrzymałem polecenie narysowania popupu dla {len(machines)} maszyn.")
        print(f"Lista maszyn z DB: {machines}")
        # W kolejnym kroku wrzucimy tu lub wywołamy cały kod budujący okienko z checkboxami