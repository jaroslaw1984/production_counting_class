import customtkinter as ctk
import tkinter as tk
import pandas as pd 
import sys
import os
import subprocess
import json
import threading
from pathlib import Path
from tkinter import messagebox
from typing import Callable
from project.config.version import (
    PROGRAM_NAME,
    PROGRAM_VERSION,
    PROGRAM_YEAR,
    PROGRAM_AUTHOR,
    DESCRIPTION,
    COMPANY_MAIL,
    PRIVATE_MAIL
    )
from project.config.paths import LATEST_JSON_PATH  

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

# --- Popup dla przycisku 'Wczytaj maszyny' ---   
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
        title = ctk.CTkLabel(self, 
                             text="Wybierz maszyny do przeliczenia", 
                             font=ctk.CTkFont(size=16, weight="bold"))
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

        save_cb = ctk.CTkCheckBox(mid_frame, 
                                  text="Zapisz terminy", 
                                  variable=self.save_snapshot_var)
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

        # --- Wykrywanie zmian w konfiguracji ---
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
        # --- Wysyłamy paczkę danych do Kontrolera! ---
        self.on_confirm(selected, pps_by_machine, self.save_snapshot_var.get(), changes, should_save_config)           

# --- Popip dla przycisku 'O programie' ---
class AboutPopup(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("O programie")
        self.resizable(False, False)
        self.grab_set()
        self.grid_columnconfigure(0, weight=1)
        center_popup(parent, self)
        
        # --- Uruchamia budowę UI (tylko jedna funkcja budująca) ---
        self._build_ui()
        
        # --- Uruchomienie sprawdzania aktualizacji ---
        self._check_update_async()
                
    def _build_ui(self):
        # --- kolumna nazwy okna --- 
        title_lbl = ctk.CTkLabel(self, 
                                 text=PROGRAM_NAME, 
                                 justify="center", 
                                 font=ctk.CTkFont(size=18, weight="bold")
                                 )
        title_lbl.grid(row=0, column=0, padx=20, pady=(18, 6), sticky="ew")
        
        # --- kolumna opisu ---
        desc_lbl = ctk.CTkLabel(self, 
                                text=DESCRIPTION.strip(), 
                                justify="center", wraplength=360, 
                                font=ctk.CTkFont(size=13))
        desc_lbl.grid(row=1, column=0, padx=20, pady=(0, 10), sticky="ew")
        
        # --- kolumna mail ---
        mail_lbl = ctk.CTkLabel(self, 
                                text=(
                                    f"Email firmowy: {COMPANY_MAIL}\n"
                                    f"Email prywatny: {PRIVATE_MAIL}"
                                    ),
                                justify="center", 
                                wraplength=360,
                                font=ctk.CTkFont(size=13)
                                )
        
        mail_lbl.grid(row=2, column=0, padx=20, pady=(0, 10), sticky="ew")
        
        # --- kolumna wersji programu
        ver_lbl = ctk.CTkLabel(self, 
                               text=f"Wersja: {PROGRAM_VERSION}", 
                               justify="center", 
                               font=ctk.CTkFont(size=13, weight="bold")
                               )
        ver_lbl.grid(row=3, column=0, padx=20, pady=(0, 6), sticky="ew")
        
        # --- zmiana statusu 
        self.status_var = tk.StringVar(value="Sprawdzam aktualizacje…")
        status_lbl = ctk.CTkLabel(self,
                                  textvariable=self.status_var,
                                  justify="center",
                                  wraplength=360,
                                  font=ctk.CTkFont(size=12),
                                  text_color="#9aa0a6"
                                  )
        status_lbl.grid(row=4, column=0, padx=20, pady=(0, 10), sticky="ew")
        
        # --- Przycisk aktualizacji (zapisany jako self, by móc go ukrywać/pokazywać w innej funkcji) ---        
        self.update_btn = ctk.CTkButton(
            self,
            text="",
            fg_color="#1f6aa5",
            hover_color="#144a73",
            command=self._on_update_click,
            )    
            
        self.update_btn.grid(row=5, column=0, padx=20, pady=(0, 12), sticky="ew")
        self.update_btn.grid_remove()  # ukryty domyślnie

        # --- Stopka ---
        footer_lbl = ctk.CTkLabel(self,
                                  text=f"© Rok: {PROGRAM_YEAR} {PROGRAM_AUTHOR}",
                                  justify="center",
                                  font=ctk.CTkFont(size=12),
                                  text_color="#9aa0a6"
                                  )
        footer_lbl.grid(row=6, column=0, padx=20, pady=(0, 12), sticky="ew")

        # --- Przycisk OK ---
        ok_btn = ctk.CTkButton(self, text="OK", command=self.destroy)
        ok_btn.grid(row=7, column=0, padx=20, pady=(0, 16))
    
    # --- sekcja aktualizacji – ukryta domyślnie, pokażmy ją tylko jeśli jest aktualizacja ---
    def _on_update_click(self):
        app_exe = Path(sys.argv[0]).resolve()
        current_app_dir = app_exe.parent
        exe_name = app_exe.name
        print("app_exe:", app_exe)
        print("current_app_dir:", current_app_dir)
        print("exe_name:", exe_name)
        self._start_updater_and_exit(current_app_dir, exe_name)            
    
    def _start_updater_and_exit(self, current_app_dir: Path, exe_name: str) -> None:
        updater_exe = current_app_dir.parent / "ProductionCounter_updater.exe"
        if not updater_exe.exists():
            messagebox.showerror("Aktualizacja", f"Brak updatera:\n{updater_exe}")
            return

        pid = os.getpid()

        subprocess.Popen(
            [
                str(updater_exe),
                "--pid", str(pid),
                "--latest_json", LATEST_JSON_PATH,
                "--current_dir", str(current_app_dir),
                "--exe_name", exe_name,
            ],
            close_fds=True,
        )

        # --- zamykamy aplikację, żeby zwolnić pliki (na 100% kończymy proces) ---
        try:
            # --- najpierw zamknij okna GUI ---
            try:
                self.destroy()
            except Exception:
                pass

            try:
                self.winfo_toplevel().destroy()
            except Exception:
                pass

            # --- twarde wyjście = brak ryzyka, że PID dalej żyje i blokuje pliki ---
            os._exit(0)
        except Exception:
            os._exit(0)   

    # --- Logika Aktualizacji ---
    def _version_tuple(self, v: str) -> tuple[int, ...]:
        """Rozbija tekst '2.0.2' na krotkę liczb (2, 0, 2), co pozwala na łatwe porównywanie z operatorem '>'"""
        try:
            return tuple(int(x) for x in str(v).strip().split("."))
        except Exception:
            return (0,)

    # --- Pobiera i odczytuje plik JSON z sieci firmowej ---
    def _fetch_latest_info(self) -> dict:
        p = Path(LATEST_JSON_PATH)
        raw = p.read_text(encoding="utf-8")
        return json.loads(raw)

    # --- Uruchamia sprawdzanie w osobnym wątku (żeby okienko nie 'wisiało') ---
    def _check_update_async(self):
        def worker():
            try:
                data = self._fetch_latest_info()
                server_version = str(data.get("version", "")).strip()
                if not server_version:
                    raise ValueError("latest.json nie ma pola 'version'")
                
                # Zamiast dotykać GUI bezpośrednio, zlecamy to głównemu wątkowi okna przez .after(0, ...)
                self.after(0, lambda: self._on_update_check_done(server_version, None))
            except Exception as e:
                self.after(0, lambda: self._on_update_check_done(None, f"{type(e).__name__}: {e}"))

        t = threading.Thread(target=worker, daemon=True)
        t.start()

    # --- Ta funkcja wywoływana jest po zakończeniu wątku i bezpiecznie aktualizuje widok ---
    def _on_update_check_done(self, server_version: str | None, error: str | None):
        if error:
            self.status_var.set(f"Nie mogę sprawdzić aktualizacji:\n{error}")
            return

        assert server_version is not None
        if self._version_tuple(server_version) > self._version_tuple(PROGRAM_VERSION):
            self.status_var.set("Dostępna aktualizacja ✅")
            self.update_btn.configure(text=f"Pobierz nową wersję: {server_version}")
            self.update_btn.grid()  # Pokazujemy ukryty wcześniej przycisk
        else:
            self.status_var.set("Posiadasz najnowszą wersję programu.")
            self.update_btn.grid_remove()            