import customtkinter as ctk
from tkinter import messagebox, filedialog
from project.GUI.popups import MachineSelectPopup, AboutPopup, HelpWindow, SchedulePopup
from project.GUI.popups import ReportParamsPopup
from project.GUI.ui_texts import ASCII_LOGO, HOME_SUBTITLE, HOME_DESC, HOME_VERSION
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
        
        # --- pływający przycisk drukowania ---
        self.print_btn = ctk.CTkButton(
            self.right,
            text="Drukuj raport",
            command=self.hanlde_print_report,
            width=120,
            height=35
        )
        
        # --- Budowa ekranu powitalnego na samym końcu ---
        self._build_welcome_screen()
        
    def _build_welcome_screen(self):
            # --- Tworzymy etykiety, jako "rodzica" podając główne pole tekstowe (self.text) ---
            self.placeholder_logo = ctk.CTkLabel(
                self.text,
                text=ASCII_LOGO,
                justify="center",
                anchor="center",
                font=ctk.CTkFont(family="Courier New", size=10)
            )
            self.placeholder_title = ctk.CTkLabel(
                self.text,
                text=HOME_SUBTITLE,
                font=ctk.CTkFont(size=18, weight="bold"),
                justify="center"
            )
            self.placeholder_desc = ctk.CTkLabel(
                self.text,
                text=HOME_DESC,
                text_color="#9aa0a6",
                font=ctk.CTkFont(size=13),
                justify="center"
            )
            self.placeholder_ver = ctk.CTkLabel(
                self.text,
                text=HOME_VERSION,
                text_color="#6f767d",
                font=ctk.CTkFont(size=12),
                justify="center"
            )
            
            # Wywołujemy pokazanie na starcie
            self.show_welcome_screen()

    def show_welcome_screen(self):
        # --- nakłada etykiety powitalne na pole tekstowe. ---
        self.placeholder_logo.place(relx=0.5, rely=0.42, anchor="center")
        self.placeholder_title.place(relx=0.5, rely=0.58, anchor="center")
        self.placeholder_desc.place(relx=0.5, rely=0.63, anchor="center")
        self.placeholder_ver.place(relx=0.5, rely=0.69, anchor="center")

    def hide_welcome_screen(self):
        # --- chowa etykiety powitalne (np. gdy pojawia się raport). ---
        self.placeholder_logo.place_forget()
        self.placeholder_title.place_forget()
        self.placeholder_desc.place_forget()
        self.placeholder_ver.place_forget()           
        
    def set_print_button_visibility(self, visible: bool):
        # --- pokazujemy lub chowamy przycisk drukowania w zależności od tego, czy mamy raport do wydrukowania ---
        if visible:
            # Używamy parametrów relatywnych, aby przycisk "pływał"
            self.print_btn.place(relx=0.97, rely=0.96, anchor="se")
        else:
            self.print_btn.place_forget()
            
    def handle_clean_text(self):
        self.state.last_report_kind = None
        self.clear_report_view()
    
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
            
    def hanlde_print_report(self):
        if hasattr(self, 'controller'):
            self.controller.handle_print_report()            
        
    def clean_text(self):
        if hasattr(self, 'controller'):
            self.controller.handle_clean_text()
            
    def clear_report_view(self):
        self.text.configure(state="normal") # Odblokuj
        self.text.delete("1.0", "end") # Wyczyść
        self.text.configure(state="disabled") # Zablokuj
        
        # --- chowanie przycisku drukowania
        self.set_print_button_visibility(False)
        
        # --- pokazanie ekranu powitalnego ---
        self.show_welcome_screen()
        
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

    # --- Ten helper jest używany przy wczytywaniu danych z pliku Excel/CSV ---
    # - otwiera dialog wyboru pliku i zwraca ścieżkę do niego (lub None, jeśli użytkownik anulował) ---
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
        
    def set_report_text(self, text):
        self.text.configure(state="normal")
        
        self.text.delete("1.0", "end") # Czyścimy stare dane
        self.hide_welcome_screen() # Ukrywamy ekran powitalny, jeśli był widoczny
        self.text.insert("1.0", text)  # Wstawiamy nowy raport
        
        # Ponownie blokujemy, żeby użytkownik przypadkiem nic nie skasował
        self.text.configure(state="disabled")
        
    def show_schedule_popup(self, on_confirm):
        SchedulePopup(self.root, on_confirm)