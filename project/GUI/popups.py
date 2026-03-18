import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
import pandas as pd 
from typing import Callable

def center_popup(parent, popup):
    try:
        parent.update_idletasks()
        popup.update_idletasks()
        pw = popup.winfo_width()
        ph = popup.winfo_height()
        rw = parent.winfo_width()
        rh = parent.winfo_height()
        rx = parent.winfo_rootx()
        ry = parent.winfo_rooty()
        x = rx + (rw - pw) // 2
        y = ry + (rh - ph) // 2
        popup.geometry(f"+{x}+{y}")
    except Exception:
        # best-effort centering — nie przerywamy działania aplikacji
        pass
    
class MachineSelectPopup(ctk.CTkToplevel):
    def __init__(self, parent, machines: list[str], df_mc: pd.DataFrame, on_confirm: Callable):
        # --- super() daje dostęp do metod klasy rodzica (czyli CTkToplevel) --- 
        super().__init__(parent)
        self.title("Wybór")
        self.geometry("620x460")
        self.resizable(False, False)
        
        self.transient(parent)
        self.grab_set()
        center_popup(parent, self)
        
        self.machines = machines
        self.df_mc = df_mc
        self.on_confirm = on_confirm
        
        self.vars_map: dict[str, tk.BooleanVar] = {}
        self.pps_vars: dict[str, tk.StringVar] = {}
        self.default_pps: dict[str, int] = {}
        self.save_snapshot_var = tk.BooleanVar(value=False)
        
        self._build_ui()
        
    def _build_ui(self):
        title = ctk.CTkLabel(self, text="Wybierz maszyny do przeliczenia", font=ctk.CTkFont(size=16, weight="bold"))
        title.pack(pady=(12,8))
        
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=12)
 
        ctk.CTkLabel(header, text="Maszyna", width=220, anchor="w").pack(side="left")
        ctk.CTkLabel(header, text="Szt./zmianę", width=120, anchor="w").pack(side="left")        
        
        scroll = ctk.CTkScrollableFrame(self, width=580, height=280)
        scroll.pack(padx=12, pady=8, fill="both", expand=True)
        
        for machine in self.machines:
            row = ctk.CTkFrame(scroll, fg_color="transparent")
            row.pack(fill="x", padx=6, pady=3)
            
            var = tk.BooleanVar(value=False)
            self.vars_map[machine] = var
            
            cb = ctk.CTkCheckBox(row, text=machine, variable=var, width=220)
            cb.pack(side="left", padx=(4, 10))
            
            pps = self._get_pps_for(machine)
            self.default_pps[machine] = pps
            sv = tk.StringVar(value=str(pps))
            self.pps_vars[machine] = sv
            
            entry = ctk.CTkEntry(row, width=120, textvariable=sv)
            entry.pack(side="left")
            ctk.CTkLabel(row, text="szt./zmianę", text_color="#aaaaaa").pack(side="left", padx=8)
            
            var.trace_add("write", lambda *args: self._refresh_toggle_btn_text())
            
        # --- Dolny pasek ---
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=12, pady=12)

        left_frame = ctk.CTkFrame(btn_frame, fg_color="transparent")
        left_frame.pack(side="left")
        mid_frame = ctk.CTkFrame(btn_frame, fg_color="transparent")
        mid_frame.pack(side="left", padx=(14, 0))
        right_frame = ctk.CTkFrame(btn_frame, fg_color="transparent")
        right_frame.pack(side="right")

        self.toggle_btn = ctk.CTkButton(left_frame, text="Wybierz wszystkie", command=self._toggle_select_all)
        self.toggle_btn.pack(side="left")

        save_cb = ctk.CTkCheckBox(mid_frame, text="Zapisz terminy", variable=self.save_snapshot_var)
        save_cb.pack(side="left")

        ctk.CTkButton(right_frame, text="Anuluj", command=self.destroy).pack(side="right", padx=(8, 0))
        ctk.CTkButton(right_frame, text="Przelicz produkcję", command=self._confirm).pack(side="right")

        self._refresh_toggle_btn_text()        
            
     
    def _get_pps_for(self, machine: str) -> int:
        row = self.df_mc.loc[self.df_mc["workplace"].astype("string").str.strip() == str(machine).strip()]
        return int(row.iloc[0]["count_by_shift"]) if not row.empty else 0

    def _all_selected(self) -> bool:
        return all(v.get() for v in self.vars_map.values()) if self.vars_map else False

    def _refresh_toggle_btn_text(self):
        self.toggle_btn.configure(text="Odznacz wszystkie" if self._all_selected() else "Wybierz wszystkie")

    def _toggle_select_all(self):
        state = not self._all_selected()
        for v in self.vars_map.values():
            v.set(state)
        self._refresh_toggle_btn_text()

    def _parse_int_or_none(self, s: str):
        s = (s or "").strip().replace(",", ".")
        if s == "": return None
        try: return int(float(s))
        except Exception: return None

    def _confirm(self):
        selected = [m for m, v in self.vars_map.items() if v.get()]
        if not selected:
            messagebox.showwarning("Brak wyboru", "Zaznacz przynajmniej jedną maszynę.")
            return

        pps_by_machine = {}
        for m in selected:
            val = self._parse_int_or_none(self.pps_vars[m].get())
            if val is None or val <= 0:
                messagebox.showerror("Błędna wartość", f"Maszyna {m}: szt./zmianę musi być > 0.")
                return
            pps_by_machine[m] = int(val)

        # Wykrywanie zmian w konfiguracji
        changes = []
        for m, sv in self.pps_vars.items():
            new_val = self._parse_int_or_none(sv.get())
            if new_val is None or new_val < 0:
                messagebox.showerror("Błędna wartość", f"Maszyna {m}: nieprawidłowa wartość.")
                return
            old_val = int(self.default_pps.get(m, 0))
            if new_val != old_val:
                changes.append((m, old_val, new_val))

        should_save_config = False
        if changes:
            preview = "\n".join([f"{m}: {old} → {new}" for (m, old, new) in changes[:12]])
            if len(changes) > 12: preview += "\n..."
            should_save_config = messagebox.askyesno(
                "Zapis do konfiguracji",
                f"Wykryto zmiany szt./zmianę:\n\n{preview}\n\nZapisać zmiany?"
            )

        self.destroy()
        # Wysyłamy paczkę danych do Kontrolera!
        self.on_confirm(selected, pps_by_machine, self.save_snapshot_var.get(), changes, should_save_config)           
            