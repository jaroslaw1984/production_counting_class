import customtkinter as ctk
from tkinter import messagebox
from project.core.config_manager import ConfigDataManager
from project.config.count_per_loader import (
    fetch_workplace_config, add_workplace, update_workplace_full, delete_workplace
)

class ConfigWindow(ctk.CTkToplevel):
    def __init__(self, parent, data_manager: ConfigDataManager):
        super().__init__(parent)
        self.data_manager = data_manager
        
        self.title("Konfiguracja danych")
        self.geometry("700x550")
        
        # Sprawia, że okno zachowuje się jak typowy popup (blokuje klikanie w główne okno)
        self.grab_set()
        
        # --- Główny kontener na zakładki ---
        self.tabview = ctk.CTkTabview(self, command=self._on_tab_changed)
        self.tabview.pack(fill="both", expand=True, padx=15, pady=15)
        
        # --- Flaga sprawdzająca, czy lista profili została już narysowana ---
        self.profiles_rendered = False
        
        # Inicjalizacja zakładek
        self.tab_ds = self.tabview.add("Maszyny obustronne")
        self.tab_machines = self.tabview.add("Park maszynowy")
        self.tab_profiles = self.tabview.add("Geometrie")
        
        # Budowa zawartości zakładek
        self._build_ds_machines_tab()
        self._build_machines_tab() 
        self._build_profiles_tab()
        
    def _on_tab_changed(self):
        """Uruchamia się przy każdym przełączeniu zakładki. Ładuje ciężkie GUI tylko w razie potrzeby."""
        selected_tab = self.tabview.get()
        
        if selected_tab == "Geometrie" and not self.profiles_rendered:
            # Pobieramy świeże dane z bazy dopiero, gdy użytkownik wejdzie w zakładkę
            self.all_profiles = self.data_manager.get_profiles()
            self._refresh_profiles_list(self.all_profiles)
            self.profiles_rendered = True

    # ==========================================
    # ZAKŁADKA 1: MASZYNY OBUSTRONNE (JSON)
    # ==========================================
    def _build_ds_machines_tab(self):
        # 1. Obszar przewijanej listy (góra)
        self.ds_scroll_frame = ctk.CTkScrollableFrame(self.tab_ds)
        self.ds_scroll_frame.pack(fill="both", expand=True, padx=10, pady=(10, 5))
        
        # 2. Formularz dodawania (dół)
        self.ds_form_frame = ctk.CTkFrame(self.tab_ds)
        self.ds_form_frame.pack(fill="x", padx=10, pady=(5, 10))
        
        self.ds_entry = ctk.CTkEntry(self.ds_form_frame, placeholder_text="Nazwa maszyny (np. Maszyna 11)")
        self.ds_entry.pack(side="left", fill="x", expand=True, padx=(10, 10), pady=10)
        
        self.ds_add_btn = ctk.CTkButton(self.ds_form_frame, text="Dodaj maszynę", command=self._add_ds_machine)
        self.ds_add_btn.pack(side="right", padx=(0, 10), pady=10)

        # Załadowanie danych przy starcie
        self._refresh_ds_list()

    def _refresh_ds_list(self):
        """Czyści listę i buduje ją na nowo na podstawie danych z pliku."""
        # Usuwanie starych widgetów z ramki
        for widget in self.ds_scroll_frame.winfo_children():
            widget.destroy()

        # Pobranie aktualnych danych
        machines = self.data_manager.get_ds_machines()

        # Generowanie wierszy
        for machine_name in machines:
            row_frame = ctk.CTkFrame(self.ds_scroll_frame, fg_color="transparent")
            row_frame.pack(fill="x", pady=2)
            
            lbl = ctk.CTkLabel(row_frame, text=machine_name, anchor="w")
            lbl.pack(side="left", padx=10)
            
            # Używamy funkcji lambda z parametrem domyślnym (m=machine_name), 
            # aby uniknąć problemu z zasięgiem zmiennych w pętli.
            del_btn = ctk.CTkButton(
                row_frame, 
                text="Usuń", 
                width=60, 
                fg_color="#D32F2F", 
                hover_color="#B71C1C",
                command=lambda m=machine_name: self._delete_ds_machine(m)
            )
            del_btn.pack(side="right", padx=10)

    def _add_ds_machine(self):
        """Obsługa przycisku dodawania."""
        new_machine = self.ds_entry.get().strip()
        if not new_machine:
            messagebox.showwarning("Błąd", "Nazwa maszyny nie może być pusta!")
            return

        success = self.data_manager.add_ds_machine(new_machine)
        if success:
            self.ds_entry.delete(0, 'end') # Czyszczenie pola
            self._refresh_ds_list()        # Odświeżenie widoku
        else:
            messagebox.showerror("Błąd", "Nie udało się zapisać maszyny lub taka maszyna już istnieje.")

    def _delete_ds_machine(self, machine_name: str):
        """Obsługa przycisku usuwania dla konkretnego wiersza."""
        # Dodatkowe potwierdzenie, żeby nikt nie usunął maszyny przez przypadek
        if messagebox.askyesno("Potwierdzenie", f"Czy na pewno chcesz usunąć '{machine_name}'?"):
            success = self.data_manager.delete_ds_machine(machine_name)
            if success:
                self._refresh_ds_list()
            else:
                messagebox.showerror("Błąd", "Nie udało się usunąć maszyny.")
                

    # ==========================================
    # ZAKŁADKA 2: MASZYNY (SQL BAZA DANYCH)
    # ==========================================
    def _build_machines_tab(self):
        self.mac_scroll_frame = ctk.CTkScrollableFrame(self.tab_machines)
        self.mac_scroll_frame.pack(fill="both", expand=True, padx=10, pady=(10, 5))
        
        self.mac_form_frame = ctk.CTkFrame(self.tab_machines)
        self.mac_form_frame.pack(fill="x", padx=10, pady=(5, 10))
        
        self.mac_wp_entry = ctk.CTkEntry(self.mac_form_frame, placeholder_text="Stanowisko (np. WLO-U001)", width=180)
        self.mac_wp_entry.pack(side="left", padx=(10, 5), pady=10)
        
        self.mac_speed_entry = ctk.CTkEntry(self.mac_form_frame, placeholder_text="Prędkość (m/min)", width=120)
        self.mac_speed_entry.pack(side="left", padx=5, pady=10)
        
        self.mac_count_entry = ctk.CTkEntry(self.mac_form_frame, placeholder_text="Sztuki/zmiana", width=120)
        self.mac_count_entry.pack(side="left", padx=5, pady=10)
        
        self.mac_save_btn = ctk.CTkButton(self.mac_form_frame, text="Zapisz", command=self._save_machine, width=100)
        self.mac_save_btn.pack(side="right", padx=(5, 10), pady=10)

        # Trzymamy tu wczytane z bazy nazwy maszyn, by wiedzieć czy robić INSERT czy UPDATE
        self.current_workplaces = [] 
        self._refresh_machines_list()

    def _refresh_machines_list(self):
        """Pobiera dane z SQL przez Pandas i rysuje listę."""
        for widget in self.mac_scroll_frame.winfo_children():
            widget.destroy()

        try:
            # Pobieramy DataFrame z bazy i zamieniamy na listę słowników
            df = fetch_workplace_config()
            machines = df.to_dict('records')
            self.current_workplaces = df['workplace'].tolist()
        except Exception as e:
            messagebox.showerror("Błąd DB", f"Nie udało się połączyć z bazą:\n{e}")
            return

        for m in machines:
            row_frame = ctk.CTkFrame(self.mac_scroll_frame, fg_color="transparent")
            row_frame.pack(fill="x", pady=2)
            
            info_text = f"{m['workplace']}  |  Prędkość: {m['speed_m_per_min']}  |  Szt.: {m['count_by_shift']}"
            lbl = ctk.CTkLabel(row_frame, text=info_text, anchor="w")
            lbl.pack(side="left", padx=10)
            
            del_btn = ctk.CTkButton(
                row_frame, text="Usuń", width=60, 
                fg_color="#D32F2F", hover_color="#B71C1C",
                command=lambda wp=m['workplace']: self._delete_machine(wp)
            )
            del_btn.pack(side="right", padx=(5, 10))
            
            edit_btn = ctk.CTkButton(
                row_frame, text="Edytuj", width=60, 
                fg_color="#1976D2", hover_color="#1565C0",
                command=lambda data=m: self._edit_machine(data)
            )
            edit_btn.pack(side="right", padx=5)

    def _edit_machine(self, m_data: dict):
        """Wrzuca dane z wybranego wiersza do pól formularza na dole."""
        self.mac_wp_entry.delete(0, 'end')
        self.mac_wp_entry.insert(0, str(m_data['workplace']))
        
        self.mac_speed_entry.delete(0, 'end')
        self.mac_speed_entry.insert(0, str(m_data['speed_m_per_min']))
        
        self.mac_count_entry.delete(0, 'end')
        self.mac_count_entry.insert(0, str(m_data['count_by_shift']))

    def _save_machine(self):
        """Sprawdza czy maszyna istnieje. Jeśli tak -> UPDATE, jeśli nie -> INSERT."""
        wp = self.mac_wp_entry.get().strip()
        speed = self.mac_speed_entry.get().strip()
        count = self.mac_count_entry.get().strip()
        
        if not wp or not speed or not count:
            messagebox.showwarning("Błąd", "Wszystkie pola muszą być wypełnione!")
            return
            
        try:
            # Konwersja na float (zabezpieczenie przed wpisaniem liter)
            speed_val = float(speed.replace(',', '.'))
            count_val = float(count.replace(',', '.'))
        except ValueError:
            messagebox.showwarning("Błąd", "Prędkość i sztuki muszą być liczbami!")
            return

        # Zapisz w zależności od tego, czy maszyna już jest w bazie
        if wp in self.current_workplaces:
            success = update_workplace_full(wp, speed_val, count_val)
        else:
            success = add_workplace(wp, speed_val, count_val)
            
        if success:
            self.mac_wp_entry.delete(0, 'end')
            self.mac_speed_entry.delete(0, 'end')
            self.mac_count_entry.delete(0, 'end')
            self._refresh_machines_list()
        else:
            messagebox.showerror("Błąd", "Nie udało się zapisać maszyny w bazie danych.")

    def _delete_machine(self, workplace: str):
        if messagebox.askyesno("Potwierdzenie", f"Czy na pewno chcesz usunąć stanowisko {workplace} z bazy?"):
            success = delete_workplace(workplace)
            if success:
                self._refresh_machines_list()
            else:
                messagebox.showerror("Błąd", "Nie udało się usunąć maszyny z bazy danych.")
                
    # ==========================================
    # ZAKŁADKA 3: GEOMETRIE / PROFILE (CSV)
    # ==========================================
    def _build_profiles_tab(self):
        # 1. Wyszukiwarka (góra)
        self.prof_search_frame = ctk.CTkFrame(self.tab_profiles, fg_color="transparent")
        self.prof_search_frame.pack(fill="x", padx=10, pady=(5, 5))
        
        self.prof_search_entry = ctk.CTkEntry(self.prof_search_frame, placeholder_text="Szukaj profilu...")
        self.prof_search_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        # --- ZMIANY: Przyciski Szukaj i Reset ---
        self.prof_search_btn = ctk.CTkButton(self.prof_search_frame, text="Szukaj", command=self._filter_profiles, width=80)
        self.prof_search_btn.pack(side="left", padx=(0, 5))
        
        self.prof_reset_btn = ctk.CTkButton(
            self.prof_search_frame, text="Reset", width=80, 
            fg_color="#555555", hover_color="#333333",
            command=self._reset_profiles_filter
        )
        self.prof_reset_btn.pack(side="left", padx=(0, 0))

        # Podpięcie klawisza Enter pod wyszukiwanie
        self.prof_search_entry.bind("<Return>", self._filter_profiles)
        
        # 2. Obszar przewijanej listy (środek)
        self.prof_scroll_frame = ctk.CTkScrollableFrame(self.tab_profiles)
        self.prof_scroll_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        # 3. Formularz (dół)
        self.prof_form_frame = ctk.CTkFrame(self.tab_profiles)
        self.prof_form_frame.pack(fill="x", padx=10, pady=(5, 10))
        
        self.prof_name_entry = ctk.CTkEntry(self.prof_form_frame, placeholder_text="Profil (np. GP8280)", width=160)
        self.prof_name_entry.pack(side="left", padx=(10, 5), pady=10)
        
        self.prof_side_entry = ctk.CTkEntry(self.prof_form_frame, placeholder_text="Strona (np. 0022)", width=120)
        self.prof_side_entry.pack(side="left", padx=5, pady=10)
        
        self.prof_time_entry = ctk.CTkEntry(self.prof_form_frame, placeholder_text="Czas (min)", width=100)
        self.prof_time_entry.pack(side="left", padx=5, pady=10)
        
        self.prof_save_btn = ctk.CTkButton(self.prof_form_frame, text="Zapisz", command=self._save_profile, width=100)
        self.prof_save_btn.pack(side="right", padx=(5, 10), pady=10)

        # Pobieramy dane z DataManager i inicjalizujemy pełną listę
        self.all_profiles = []

    def _filter_profiles(self, event=None):
        """Filtruje listę na podstawie wpisanego tekstu w wyszukiwarce."""
        search_term = self.prof_search_entry.get().strip().upper()
        if not search_term:
            filtered = self.all_profiles
        else:
            filtered = [p for p in self.all_profiles if search_term in p['profile'].upper()]
        
        self._refresh_profiles_list(filtered)
        
    def _reset_profiles_filter(self):
        """Czyści pole wyszukiwania i odświeża listę do pełnego stanu."""
        self.prof_search_entry.delete(0, 'end')
        self._filter_profiles()

    def _refresh_profiles_list(self, profiles_to_show: list):
        """Czyści i buduje listę profili."""
        for widget in self.prof_scroll_frame.winfo_children():
            widget.destroy()

        for p in profiles_to_show:
            row_frame = ctk.CTkFrame(self.prof_scroll_frame, fg_color="transparent")
            row_frame.pack(fill="x", pady=2)
            
            info_text = f"Profil: {p['profile']}  |  Strona: {p['side']}  |  Czas: {p['setting_time']} min"
            lbl = ctk.CTkLabel(row_frame, text=info_text, anchor="w")
            lbl.pack(side="left", padx=10)
            
            # Przekazujemy oba klucze: profil i stronę
            del_btn = ctk.CTkButton(
                row_frame, text="Usuń", width=60, 
                fg_color="#D32F2F", hover_color="#B71C1C",
                command=lambda prof=p['profile'], side=p['side']: self._delete_profile(prof, side)
            )
            del_btn.pack(side="right", padx=(5, 10))
            
            edit_btn = ctk.CTkButton(
                row_frame, text="Edytuj", width=60, 
                fg_color="#1976D2", hover_color="#1565C0",
                command=lambda data=p: self._edit_profile(data)
            )
            edit_btn.pack(side="right", padx=5)

    def _edit_profile(self, p_data: dict):
        """Wrzuca dane z wybranego wiersza do formularza na dole."""
        self.prof_name_entry.delete(0, 'end')
        self.prof_name_entry.insert(0, p_data['profile'])
        
        self.prof_side_entry.delete(0, 'end')
        self.prof_side_entry.insert(0, p_data['side'])
        
        self.prof_time_entry.delete(0, 'end')
        self.prof_time_entry.insert(0, p_data['setting_time'])

    def _save_profile(self):
        """Dodaje nowy lub aktualizuje czas zbrojenia istniejącego profilu."""
        prof = self.prof_name_entry.get().strip().upper()  # Wymuszamy wielkie litery dla porządku
        side = self.prof_side_entry.get().strip()
        time_val = self.prof_time_entry.get().strip()
        
        if not prof or not side or not time_val:
            messagebox.showwarning("Błąd", "Wszystkie pola muszą być wypełnione!")
            return
            
        success = self.data_manager.save_profile(prof, side, time_val)
        if success:
            self.prof_name_entry.delete(0, 'end')
            self.prof_side_entry.delete(0, 'end')
            self.prof_time_entry.delete(0, 'end')
            
            # Odświeżenie danych z pliku i zresetowanie wyszukiwarki
            self.all_profiles = self.data_manager.get_profiles()
            self.prof_search_entry.delete(0, 'end')
            self._refresh_profiles_list(self.all_profiles)
        else:
            # Zmiana komunikatu błędu
            messagebox.showerror("Błąd", "Nie udało się zapisać profilu w bazie danych SQL. Sprawdź połączenie.")

    def _delete_profile(self, profile: str, side: str):
        if messagebox.askyesno("Potwierdzenie", f"Czy na pewno usunąć profil {profile} (strona {side})?"):
            success = self.data_manager.delete_profile(profile, side)
            if success:
                self.all_profiles = self.data_manager.get_profiles()
                # Ponowne wywołanie filtru pozwala zachować wyniki wyszukiwania po usunięciu
                self._filter_profiles()
            else:
                # Zmiana komunikatu błędu
                messagebox.showerror("Błąd", "Nie udało się usunąć profilu z bazy danych.")