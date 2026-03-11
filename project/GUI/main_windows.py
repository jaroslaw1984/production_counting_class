from turtle import left, right
import customtkinter as ctk
from project.core.app_state import AppState

class MainWindow:
    def __init__(self, state: AppState):
        self.state = state
        
        # Konfiguracja wyglądu
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
                
        # Root window
        self.root = ctk.CTk()
        self.root.title("Policz produkcję")
        self.root.geometry("800x600")
        
        # Ustawienia czcionki
        self.default_font = ctk.CTkFont(family="Segoe UI", size=14, weight="bold")
       
        # Budowa UI
        self._configure_layout()
        self._build_left_panel()
        self._build_right_panel()
    
    # Budowa lewej części (panel boczny)    
    def _build_left_panel(self):
        self.left = ctk.CTkFrame(self.root)
        self.left.grid(row=0, column=0, sticky="ns", padx=10, pady=10)
        self.left.grid_columnconfigure(0, weight=1) # tylko góra-dół
        self.left.grid_rowconfigure(98, weight=1)  # push przyciski do góry
    
        # --- definicja przycisków (tekst, handler) ---
        buttons = [
            ("Wczytaj maszyny", self.loading_machine_data),
            ("Wczytaj plik", self.on_open_file),
            ("Przelicz produkcję", self.calculate_production),
            ("Generuj raport", self.generate_logistics_report),
            ("Wyczyść", self.clean_text),
            ("Jasny motyw" , self.change),
            
        ]
    
        # --- tworzenie przycisków w pętli ---
        for row, (label, handler) in enumerate(buttons):
            btn = ctk.CTkButton(
                self.left,
                text=label,
                command=handler
            )
            btn.grid(row=row, column=0, sticky="ew", padx=10, pady=10)
            
        self.theme_button = ctk.CTkButton(
            self.left,
            text=self._get_theme_button_text(),
            command=self.change_theme
        )
    
    # Budowa prawej części (główna)    
    def _build_right_panel(self):
        # 3) Prawa część (rośnie w obie strony 
        self.right = ctk.CTkFrame(self.root)
        self.right.grid(row=0, column=1, sticky="nsew", padx=10, pady=10) # rośnie w obie strony

        # 4) Wnętrze prawego panelu też robimy responsywne
        self.right.grid_columnconfigure(0, weight=1)
        self.right.grid_rowconfigure(0, weight=0)  # toolbar
        self.right.grid_rowconfigure(1, weight=1)  # treść (textbox / tabela)        

        self.text = ctk.CTkTextbox(self.right)
        self.text.grid(row=1, column=0, sticky="nsew")
        self.text.configure(state="disabled") 
        
    def _get_theme_button_text(self) -> str:
        return "Jasny motyw" if ctk.get_appearance_mode() == "dark" else "Ciemny motyw"
    
    def change_theme(self):
        if ctk.get_appearance_mode() == "light":
            ctk.set_appearance_mode("dark")
        else:
            ctk.set_appearance_mode("light")
            
        # aktualizacja tekstu przycisku
        self.theme_button.configure(text=self._get_theme_button_text())
        
        # Konfiguracja layoutu root window          
    def _configure_layout(self):    
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)
        
    def loading_machine_data(self):
        print("Ładowanie danych maszyn...")
        
    def on_open_file(self):
        print("Otwieranie pliku...")
        
    def calculate_production(self):
        print("Liczenie produkcji...")
        
    def generate_logistics_report(self):
        print("Generowanie raportu logistycznego...")
        
    def clean_text(self):
        print("Czyszczenie tekstu...")
        
    def change(self):
        print("Zmiana motywu...")

    def run(self):
        self.root.mainloop()