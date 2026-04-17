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
        self.root.geometry("840x640")
        
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
        self.right.grid_rowconfigure(2, weight=0) 
        
        # --- Pasek akcji na dole prawego panelu ---
        self.action_frame = ctk.CTkFrame(self.right, fg_color="transparent")
        self.action_frame.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        self.action_frame.grid_remove() # Domyślnie ukryte
        
        self.edit_btn = ctk.CTkButton(
            self.action_frame, text="Edytuj raport", command=self.handle_edit_report, width=140, height=35
        )

        self.print_btn = ctk.CTkButton(
            self.action_frame, text="Drukuj raport", command=self.hanlde_print_report, width=140, height=35
        )
        
        self._build_welcome_screen()
        
    def _build_welcome_screen(self):
        # Cała powierzchnia
        self.welcome_frame = ctk.CTkFrame(self.right, fg_color="transparent")
        
        # Centralna karta (Card) z delikatnym tłem
        self.welcome_inner = ctk.CTkFrame(self.welcome_frame, fg_color=("#e5e5e5", "#1e1e1e"), corner_radius=15)
        self.welcome_inner.place(relx=0.5, rely=0.5, anchor="center")

        # Logo ASCII z błękitnym akcentem kolorystycznym!
        self.placeholder_logo = ctk.CTkLabel(
            self.welcome_inner, 
            text=ASCII_LOGO,
            justify="center",
            text_color=("#2980b9", "#85c1e9"), # Głęboki fiolet / Jasny, pastelowy fiolet
            font=ctk.CTkFont(family="Courier New", size=10, weight="bold")
        )
        self.placeholder_logo.pack(pady=(30, 15), padx=40)

        self.placeholder_title = ctk.CTkLabel(
            self.welcome_inner,
            text=HOME_SUBTITLE,
            font=ctk.CTkFont(size=18, weight="bold"),
            justify="center"
        )
        self.placeholder_title.pack(pady=(0, 5), padx=40)

        self.placeholder_desc = ctk.CTkLabel(
            self.welcome_inner,
            text=HOME_DESC,
            text_color="#9aa0a6",
            font=ctk.CTkFont(size=13),
            justify="center"
        )
        self.placeholder_desc.pack(pady=(0, 5), padx=40)

        self.placeholder_ver = ctk.CTkLabel(
            self.welcome_inner,
            text=HOME_VERSION,
            text_color="#a86b47",
            font=ctk.CTkFont(size=12, weight="bold"),
            justify="center"
        )
        self.placeholder_ver.pack(pady=(0, 30))
        
        self.show_welcome_screen()

    def show_welcome_screen(self):
        self.welcome_frame.grid(row=1, column=0, sticky="nsew")
        
    def hide_welcome_screen(self):
        # Chowamy ramkę startową
        if hasattr(self, "welcome_frame"):
            self.welcome_frame.grid_remove()        
        
    def set_print_button_visibility(self, visible: bool):
            # --- pokazujemy lub chowamy cały dolny pasek akcji ---
            if visible:
                self.action_frame.grid()
                
                # Najpierw bezwzględnie czyścimy układ, żeby zapobiec nakładaniu się przycisków (bug z CustomTkinter)
                self.print_btn.pack_forget()
                self.edit_btn.pack_forget()
                
                # Pakujemy od prawej do lewej: najpierw "Drukuj" na sam prawy skraj
                self.print_btn.pack(side="right")
                
                # Jeśli to raport SAP, dokładamy "Edytuj" na lewo od przycisku drukowania (z małym odstępem)
                if self.state.last_report_kind == "sap":
                    self.edit_btn.pack(side="right", padx=(0, 10))
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
        # 1. Usuń wszystko z prawej strony
        self._cleanup_table()
        
        # 2. Schowaj przyciski
        self.set_print_button_visibility(False)
        
        # 3. Pokaż nowy ekran powitalny
        self.show_welcome_screen()

    def _cleanup_table(self):
        """Pancerne usuwanie widoków raportów."""
        if hasattr(self, "table_frame") and self.table_frame is not None:
            try:
                self.table_frame.grid_forget() # Wymusza zdjęcie ze sceny
                if self.table_frame.winfo_exists():
                    self.table_frame.destroy()
            except Exception:
                pass
            finally:
                self.table_frame = None
        
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
        self._cleanup_table() 
        self.hide_welcome_screen() 
        
        # Używamy zaufanego ScrollableFrame zamiast brzydkiego textarea
        self.table_frame = ctk.CTkScrollableFrame(self.right, fg_color="transparent")
        self.table_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)

        # Tworzymy elegancką kartę dla podsumowania
        card = ctk.CTkFrame(self.table_frame, fg_color=("#f2f2f2", "#242424"), corner_radius=10)
        card.pack(pady=20, padx=20, fill="x")

        # Formatujemy tekst czcionką stałoszerokościową, by wszystko było równiutko
        lbl = ctk.CTkLabel(
            card,
            text=text,
            font=ctk.CTkFont(family="Consolas", size=14), 
            justify="left",
            text_color=("#111111", "#e0e0e0")
        )
        lbl.pack(pady=20, padx=20, anchor="w")
        
    def show_schedule_popup(self, on_confirm):
        SchedulePopup(self.root, on_confirm)
        
    def render_sap_report_table(self, linia: str, day: str, rows: list[dict], user: str = ""):
        """Renderuje profesjonalną tabelę raportu SAP przy użyciu natywnych widżetów CustomTkinter."""
        # --- Najpierw czyścimy poprzednią tabelę, jeśli istniała (np. z raportu bazy danych) ---
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

        # --- DYNAMICZNY PODTYTUŁ Z UŻYTKOWNIKIEM ---
        sub_text = f"Linia: {linia}  |  Dzień: {day}"
        if user:
            sub_text += f"  |  Planista: {user}"

        sub_lbl = ctk.CTkLabel(
            self.table_frame, 
            text=sub_text, 
            font=ctk.CTkFont(size=14),
            text_color=("#555555", "#9aa0a6") # <--- Krotka: (Jasny, Ciemny)
        )
        sub_lbl.pack(anchor="w", pady=(0, 15), padx=10)

        # --- RAMKA TABELI ---
        table_content = ctk.CTkFrame(self.table_frame, fg_color="transparent")
        table_content.pack(fill="x", padx=10)
        
        # Konfiguracja szerokości kolumn (siatka)
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
            
    def render_db_report_cards(self, report_text: str):
        """Renderuje eleganckie karty dla raportu z bazy danych (Wczytaj maszyny)."""
        # --- Najpierw czyścimy poprzednią tabelę, jeśli istniała (np. z raportu SAP) ---
        self._cleanup_table()
            
        # 2. Resetujemy kontener, jeśli wcześniej był użyty (np. przez raport SAP)
        if hasattr(self, "table_frame") and self.table_frame:
            self.table_frame.destroy()

        self.table_frame = ctk.CTkScrollableFrame(self.right, fg_color="transparent")
        self.table_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)

        # --- NAGŁÓWEK GŁÓWNY ---
        header_lbl = ctk.CTkLabel(
            self.table_frame, 
            text="PRZEWIDYWANE ZAKOŃCZENIE PRODUKCJI", 
            font=ctk.CTkFont(size=18, weight="bold")
        )
        header_lbl.pack(anchor="w", pady=(10, 15), padx=10)

        # --- INTELIGENTNE PARSOWANIE TEKSTU ---
        machines_data = []
        current = None
        
        for line in report_text.splitlines():
            line = line.strip()
            if not line or "Przewidywane zakończenie produkcji" in line:
                continue
            
            # Nowa maszyna
            if line.startswith("===") and line.endswith("==="):
                if current:
                    machines_data.append(current)
                current = {
                    "name": line.replace("=", "").strip(), 
                    "details": [], 
                    "end": "", 
                    "warning": ""
                }
                continue
                
            if current is not None:
                if line.startswith("Przewidywana produkcja do:"):
                    current["end"] = line.replace("Przewidywana produkcja do:", "").strip()
                elif line.startswith("⚠️"):
                    current["warning"] += line + "\n"
                elif line.startswith("---"): 
                    continue # Pomijamy linię oddzielającą
                elif "Brak danych" in line:
                    current["details"].append(("Status", "Brak danych w bazie (SQL)"))
                else:
                    if ":" in line:
                        k, v = line.split(":", 1)
                        current["details"].append((k.strip(), v.strip()))
                    else:
                        # Doklejamy np. linie z listą profili bez configu do ostrzeżenia
                        if current.get("warning") is not None:
                             current["warning"] += line + "\n"
        
        # Zapisz ostatnią maszynę z pętli
        if current:
            machines_data.append(current)

        # --- RYSOWANIE KART (Cards) ---
        for m_data in machines_data:
            # Tło karty
            card = ctk.CTkFrame(self.table_frame, fg_color=("#f2f2f2", "#242424"), corner_radius=8)
            card.pack(fill="x", padx=10, pady=(0, 15))

            # Header karty (Nazwa maszyny)
            header_row = ctk.CTkFrame(card, fg_color=("#e5e5e5", "#4D4C4C"), height=40)
            header_row.pack(fill="x")
            header_row.pack_propagate(False) # Blokuje zmianę wysokości
            
            lbl_name = ctk.CTkLabel(
                header_row, 
                text=m_data["name"], 
                font=ctk.CTkFont(size=16, weight="bold"),
                text_color=("#1f6aa5", "#7ba1c7")
            )
            lbl_name.pack(side="left", padx=15)

            # Kontener na szczegóły
            content_frame = ctk.CTkFrame(card, fg_color="transparent")
            content_frame.pack(fill="x", padx=15, pady=10)

            # Wiersze z danymi (Klucz: Wartość)
            for key, val in m_data["details"]:
                row = ctk.CTkFrame(content_frame, fg_color="transparent")
                row.pack(fill="x", pady=2)
                
                lbl_k = ctk.CTkLabel(
                    row, text=key + ":", 
                    font=ctk.CTkFont(size=13), 
                    text_color=("#555555", "#aaaaaa"), 
                    width=170, 
                    anchor="w"
                )
                lbl_k.pack(side="left")
                
                lbl_v = ctk.CTkLabel(
                    row, text=val, 
                    font=ctk.CTkFont(size=13, weight="bold"), 
                    text_color=("#111111", "#ffffff"), 
                    anchor="w"
                )
                lbl_v.pack(side="left", fill="x", expand=True)

            # Ostrzeżenia (Pomarańczowy akcent)
            if m_data.get("warning"):
                warn_lbl = ctk.CTkLabel(
                    card, 
                    text=m_data["warning"].strip(), 
                    text_color=("#c86400", "#e68a00"), 
                    font=ctk.CTkFont(size=12, slant="italic"),
                    justify="left"
                )
                warn_lbl.pack(anchor="w", padx=15, pady=(0, 10))

            # Stopka Terminu (Zielony akcent)
            if m_data.get("end"):
                end_frame = ctk.CTkFrame(card, fg_color=("#d4edda", "#1c3b24"), corner_radius=6)
                end_frame.pack(fill="x", padx=15, pady=(5, 15))
                
                end_title = ctk.CTkLabel(
                    end_frame, text="Przewidywana produkcja do:", 
                    font=ctk.CTkFont(size=13), 
                    text_color=("#155724", "#85c894")
                )
                end_title.pack(side="left", padx=10, pady=8)
                
                end_val = ctk.CTkLabel(
                    end_frame, text=m_data["end"], 
                    font=ctk.CTkFont(size=14, weight="bold"), 
                    text_color=("#0c3815", "#a3e5b3")
                )
                end_val.pack(side="right", padx=10, pady=8)