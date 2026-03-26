import customtkinter as ctk
from tkinter import messagebox, filedialog
from project.GUI.popups import MachineSelectPopup, AboutPopup, HelpWindow
from project.GUI.popups import ReportParamsPopup
from project.core.app_state import AppState

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
        self.left.grid_columnconfigure(0, weight=1) 
        self.left.grid_rowconfigure(1, weight=1)  
        
        # --- górne przyciski ---
        self.top_frame = ctk.CTkFrame(self.left, fg_color="transparent")
        self.top_frame.grid(row=0, column=0, sticky="ns", pady=(10, 10))
        self.top_frame.grid_columnconfigure(0, weight=1)        
    
        # --- dolne przyciski ---
        self.down_frame = ctk.CTkFrame(self.left, fg_color="transparent")
        self.down_frame.grid(row=2, column=0, sticky="ns", pady=(10, 10))
        self.down_frame.grid_columnconfigure(0, weight=1)
               
        # --- definicja dla górnych przycisków (bez martwego kodu!) ---
        top_buttons = [
            ("Wczytaj maszyny", self.loading_machine_data),
            ("Generuj raport", self.generate_logistics_report),
            ("Potwierdź termin", self.confirm_order),
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
            
        # --- Ręczna definicja przycisku motywu ---
        self.theme_button = ctk.CTkButton(
            self.down_frame,
            text=self._get_theme_button_text(), 
            command=self.change_theme,
            font=self.default_font
        )
        self.theme_button.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
             
        # --- definicja dolnych przycisków ---     
        bottom_buttons = [
            ("Pomoc", self.help_btn),
            ("O programie", self.about_btn)  
        ]
        
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
        self.right = ctk.CTkFrame(self.root)
        self.right.grid(row=0, column=1, sticky="nsew", padx=10, pady=10) 

        self.right.grid_columnconfigure(0, weight=1)
        self.right.grid_rowconfigure(0, weight=0)  
        self.right.grid_rowconfigure(1, weight=1)       

        self.text = ctk.CTkTextbox(self.right)
        self.text.grid(row=1, column=0, sticky="nsew")
        self.text.configure(state="disabled") 
    
    def _get_theme_button_text(self) -> str:
        return "Jasny motyw" if ctk.get_appearance_mode() == "Dark" else "Ciemny motyw"
    
    def change_theme(self):
        if ctk.get_appearance_mode() == "Light":
            ctk.set_appearance_mode("Dark")
        else:
            ctk.set_appearance_mode("Light")
        self.theme_button.configure(text=self._get_theme_button_text())
               
    def _configure_layout(self):    
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

    # # # # # # # # # # # # # # # # # # # # # # # # # #
    # Przekierowania akcji przycisków do Kontrolera   #
    # # # # # # # # # # # # # # # # # # # # # # # # # #
        
    def loading_machine_data(self):
        if hasattr(self, 'controller'):
            self.controller.handle_load_machines()
        
    def generate_logistics_report(self):
        if hasattr(self, 'controller'):
            self.controller.handle_generate_report()
        
    def confirm_order(self):
        if hasattr(self, 'controller'):
            self.controller.handle_confirm_order()
        
    def clean_text(self):
        print("Czyszczenie tekstu...") # Tym zajmiemy się na samym końcu
        
    def help_btn(self):
        HelpWindow(self.root)
        
    def about_btn(self):
        AboutPopup(self.root)

    def run(self):
        self.root.mainloop()
        
    # # # # # # # # # # # # # # # # # # # # # #
    # Helpery dla kontrolera (controllers.py) #
    # # # # # # # # # # # # # # # # # # # # # #
    
    def show_error(self, title: str, message: str):
        messagebox.showerror(title, message)
        
    def show_warning(self, title: str, message: str):
        messagebox.showwarning(title, message)
        
    def show_machine_select_popup(self, machines: list[str], df_mc, on_confirm):
        MachineSelectPopup(self.root, machines, df_mc, on_confirm)

    # UNIWERSALNA FUNKCJA POBIERANIA ŚCIEŻKI DO PLIKU
    def ask_for_file_path(self, title="Wybierz plik Excel/CSV") -> str | None:
        file_path = filedialog.askopenfilename(
            title=title,
            filetypes=[
                ("Excel files", ("*.xlsx", "*.xls")),
                ("CSV files", ("*.csv",)),
                ("All files", ("*.*",)),
            ],
        )
        return file_path if file_path else None
    
    def show_report_params_popup(self, machines: list[str], on_confirm):
        ReportParamsPopup(self.root, machines, on_confirm)