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
            self.right.grid_rowconfigure(1, weight=1) # Tabela będzie się rozciągać
            self.right.grid_rowconfigure(2, weight=0) # Pasek przycisków zawsze na dole       

            self.text = ctk.CTkTextbox(self.right)
            self.text.grid(row=1, column=0, sticky="nsew")
            self.text.configure(state="disabled") 
            
            # --- Pasek akcji na dole prawego panelu (Drukuj, Edytuj) ---
            self.action_frame = ctk.CTkFrame(self.right, fg_color="transparent")
            self.action_frame.grid(row=2, column=0, sticky="ew", pady=(10, 0))
            self.action_frame.grid_remove() # Domyślnie ukryte
            
            self.edit_btn = ctk.CTkButton(
                self.action_frame,
                text="Edytuj raport",
                command=self.handle_edit_report,
                width=140,
                height=35
            )
            self.edit_btn.pack(side="right", padx=(10, 0))

            self.print_btn = ctk.CTkButton(
                self.action_frame,
                text="Drukuj raport",
                command=self.hanlde_print_report,
                width=140,
                height=35
            )
            self.print_btn.pack(side="right")
            
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
            # --- pokazujemy lub chowamy cały dolny pasek akcji ---
            if visible:
                self.action_frame.grid()
                # Jeśli to raport SAP, pokaż też przycisk Edytuj. Jeśli DB - schowaj go.
                if self.state.last_report_kind == "sap":
                    self.edit_btn.pack(side="right", padx=(10, 0))
                else:
                    self.edit_btn.pack_forget()
            else:
                self.action_frame.grid_remove()

    def handle_edit_report(self):
        if hasattr(self, 'controller'):
            self.controller.handle_edit_report()
            
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
            # 1. Usuń ładną tabelę, jeśli istnieje
            if hasattr(self, "table_frame") and self.table_frame:
                self.table_frame.destroy()
                self.table_frame = None
                
            # 2. Przywróć główny Textbox, jeśli był ukryty
            if hasattr(self, "text"):
                self.text.grid(row=1, column=0, sticky="nsew")
                self.text.configure(state="normal") # Odblokuj
                self.text.delete("1.0", "end") # Wyczyść
                self.text.configure(state="disabled") # Zablokuj
            
            # 3. Schowaj przycisk drukowania
            self.set_print_button_visibility(False)
            
            # 4. Pokaż ekran powitalny
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
        
    def render_sap_report_table(self, linia: str, day: str, rows: list[dict]):
            """Renderuje profesjonalną tabelę raportu SAP przy użyciu natywnych widżetów CustomTkinter."""
            
            if hasattr(self, "text") and self.text:
                self.text.grid_remove() 
            self.hide_welcome_screen()
                
            if hasattr(self, "table_frame") and self.table_frame:
                self.table_frame.destroy()

            self.table_frame = ctk.CTkScrollableFrame(self.right, fg_color="transparent")
            self.table_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)

            # --- NAGŁÓWEK RAPORTU ---
            header_lbl = ctk.CTkLabel(
                self.table_frame, 
                text="RAPORT DOTYCZĄCY ZAPOTRZEBOWANIA POD OKLEJANIE", 
                font=ctk.CTkFont(size=18, weight="bold")
            )
            header_lbl.pack(anchor="w", pady=(10, 2), padx=10)

            sub_lbl = ctk.CTkLabel(
                self.table_frame, 
                text=f"Linia: {linia}  |  Dzień: {day}", 
                font=ctk.CTkFont(size=14),
                text_color=("#555555", "#9aa0a6") # <--- Krotka: (Jasny, Ciemny)
            )
            sub_lbl.pack(anchor="w", pady=(0, 15), padx=10)

            # --- RAMKA TABELI ---
            table_content = ctk.CTkFrame(self.table_frame, fg_color="transparent")
            table_content.pack(fill="x", padx=10)
            
            table_content.grid_columnconfigure(0, weight=0, minsize=40)  # LP
            table_content.grid_columnconfigure(1, weight=1)              # INDEKS
            table_content.grid_columnconfigure(2, weight=0, minsize=100) # ILOŚĆ
            table_content.grid_columnconfigure(3, weight=0, minsize=50)  # JM
            table_content.grid_columnconfigure(4, weight=0, minsize=80)  # SZT

            # --- NAGŁÓWKI KOLUMN TABELI ---
            headers = ["LP", "INDEKS", "ILOŚĆ", "JM", "SZT"]
            for col_idx, text in enumerate(headers):
                lbl = ctk.CTkLabel(
                    table_content, 
                    text=text, 
                    font=ctk.CTkFont(size=13, weight="bold"),
                    text_color=("#1f6aa5", "#7ba1c7"), # <--- Akcent w obu trybach
                    anchor="w" if col_idx < 2 else "e" 
                )
                lbl.grid(row=0, column=col_idx, sticky="ew", padx=10, pady=5)

            # Linia oddzielająca
            separator = ctk.CTkFrame(table_content, height=2, fg_color=("#cccccc", "#3a3a3a"))
            separator.grid(row=1, column=0, columnspan=5, sticky="ew", pady=(0, 5))

            # --- WIERSZE Z DANYMI (Zebra kompatybilna z motywami) ---
            for row_idx, r_data in enumerate(rows):
                # Parametr: (KolorJasny, KolorCiemny)
                bg_color = ("#f2f2f2", "#2b2b2b") if row_idx % 2 == 0 else ("#e5e5e5", "#242424")
                
                row_frame = ctk.CTkFrame(table_content, fg_color=bg_color, corner_radius=4)
                row_frame.grid(row=row_idx + 2, column=0, columnspan=5, sticky="ew", pady=1)
                
                values = [
                    f"{r_data['lp']}.", 
                    r_data['index'], 
                    f"{float(r_data['qty']):.1f}", 
                    r_data['jm'], 
                    str(r_data['szt'])
                ]
                
                for col_idx, val in enumerate(values):
                    lbl = ctk.CTkLabel(
                        row_frame, 
                        text=val, 
                        font=ctk.CTkFont(size=13),
                        text_color=("#111111", "#ffffff"), # Wyraźny tekst
                        anchor="w" if col_idx < 2 else "e"
                    )
                    lbl.grid(row=0, column=col_idx, sticky="ew", padx=10, pady=4)
                
                row_frame.grid_columnconfigure(0, weight=0, minsize=40)
                row_frame.grid_columnconfigure(1, weight=1)
                row_frame.grid_columnconfigure(2, weight=0, minsize=100)
                row_frame.grid_columnconfigure(3, weight=0, minsize=50)
                row_frame.grid_columnconfigure(4, weight=0, minsize=80)