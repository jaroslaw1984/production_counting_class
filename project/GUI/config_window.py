import customtkinter as ctk
from tkinter import messagebox
from typing import Callable
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
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=15, pady=15)
        
        # Inicjalizacja zakładek
        self.tab_ds = self.tabview.add("Maszyny obustronne")
        self.tab_machines = self.tabview.add("Maszyny")
        self.tab_profiles = self.tabview.add("Geometrie")
        
        # Budowa zawartości zakładek
        self._build_ds_machines_tab()
        self._build_machines_tab() 
        # self._build_profiles_tab()  # <- Tym zajmiemy się w kolejnym kroku

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