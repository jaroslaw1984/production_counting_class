import customtkinter as ctk
from tkinter import messagebox
from typing import Callable
from project.core.config_manager import ConfigDataManager

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
        # self._build_machines_tab()  <- Tym zajmiemy się w kolejnym kroku
        # self._build_profiles_tab()  <- Tym zajmiemy się w kolejnym kroku

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