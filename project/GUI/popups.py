import customtkinter as ctk
import tkinter as tk
import pandas as pd 
import sys
import os
import subprocess
import json
import threading
from datetime import date, datetime
from PIL import Image
from pathlib import Path
from tkinter import messagebox
from typing import Callable, Tuple
from project.config.version import (
    PROGRAM_NAME,
    PROGRAM_VERSION,
    PROGRAM_YEAR,
    PROGRAM_AUTHOR,
    DESCRIPTION,
    COMPANY_MAIL,
    PRIVATE_MAIL
    )
from project.config.paths import LATEST_JSON_PATH, HELP_SECTIONS_PATH, HELP_SECTIONS_IMAGES 

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

    # # # # # # # # # # # # # # # # # # # # # # 
    # Popup dla przycisku 'Wczytaj maszyny'   #
    # # # # # # # # # # # # # # # # # # # # # # 

class MachineSelectPopup(ctk.CTkToplevel):
    def __init__(self, parent, machines: list[str], df_mc: pd.DataFrame, on_confirm: Callable):
        # --- super() daje dostęp do metod klasy rodzica (czyli CTkToplevel) --- 
        super().__init__(parent)
        self.title("Wybór")
        self.geometry("640x460")
        self.resizable(False, False)
        
        self.transient(parent)
        self.grab_set()
        center_popup(parent, self)
        
        self.machines = machines
        self.df_mc = df_mc
        self.on_confirm = on_confirm
        
        self.vars_map: dict[str, tk.BooleanVar] = {} # mapa: maszyna -> czy zaznaczona
        self.pps_vars: dict[str, tk.StringVar] = {} # mapa: maszyna -> wartość szt./zmianę (string, bo to jest tekst w Entry)
        self.saturday_vars: dict[str, tk.BooleanVar] = {} # mapa: maszyna -> czy to jest sobota (checkbox)
        self.sunday_vars: dict[str, tk.BooleanVar] = {} # mapa: maszyna -> czy to jest niedziela (checkbox)
        self.default_pps: dict[str, int] = {} # mapa: maszyna -> domyślna wartość szt./zmianę (z DF, do porównania przy zapisie)
        self.save_snapshot_var = tk.BooleanVar(value=False) # czy zapisać terminy do snapshotu (checkbox w popupie)
        
        self._build_ui()
        
    def _build_ui(self):
        title = ctk.CTkLabel(self, 
                             text="Wybierz maszyny do przeliczenia", 
                             font=ctk.CTkFont(size=16, weight="bold"))
        title.pack(pady=(12,8))
        
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=14)
 
        ctk.CTkLabel(header, text="Maszyna", width=260, anchor="w").pack(side="left")
        ctk.CTkLabel(header, text="Szt./zmianę", width=200, anchor="w").pack(side="left")
        ctk.CTkLabel(header, text="Sob.", width=80, anchor="center").pack(side="left")
        ctk.CTkLabel(header, text="Niedz.", width=80, anchor="center").pack(side="left")         
        
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
            
            # --- dodajemy checkbox weekendowy sobota --- 
            saturday_var = tk.BooleanVar(value=False)
            self.saturday_vars[machine] = saturday_var
            saturday_cb = ctk.CTkCheckBox(row, text="", variable=saturday_var, width=40)
            saturday_cb.pack(side="left", padx=(40, 0))
            
            # --- dodajemy checkbox weekendowy niedziela ---
            sunday_var = tk.BooleanVar(value=False)
            self.sunday_vars[machine] = sunday_var
            sunday_cb = ctk.CTkCheckBox(row, text="", variable=sunday_var, width=40)
            sunday_cb.pack(side="left", padx=(40, 0))
            
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
        
        # --- tworzymy słownik: która z WYBRANYCH maszyn ma pracować w sobotę ---
        saturday_by_machine = {m: self.saturday_vars[m].get() for m in selected}        
        # --- tworzymy słownik: która z WYBRANYCH maszyn ma pracować w niedzielę
        sunday_by_machine = {m: self.sunday_vars[m].get() for m in selected}        

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
        # Dodajemy saturday_by_machine jako trzeci argument (zmieniamy kolejność/ilość argumentów)
        self.on_confirm(selected, pps_by_machine, saturday_by_machine, sunday_by_machine, self.save_snapshot_var.get(), changes, should_save_config)           

    # # # # # # # # # # # # # # # # # # # # 
    # Popup dla przycisku 'O programie'   #
    # # # # # # # # # # # # # # # # # # # # 

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
            
    # # # # # # # # # # 
    # Sekcja "Pomoc"  #
    # # # # # # # # # # 

class HelpWindow(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Pomoc")
        self.geometry("780x720")
        self.minsize(680, 520)
        center_popup(parent, self)
        
        # --- Zatrzymanie okna na wierzchu ---
        self.transient(parent)
        self.lift()
        self.focus_force()
        
        # --- Stan akordeonu (zabezpieczenie przed usunięciem przez Garbage Collector) ---
        self.opened_content = None
        self.opened_chev = None
        self._images = []  # Kluczowe! Jeśli nie przypiszesz obrazków do self, znikną z ekranu!
        
        # --- Stałe konfiguracyjne dla animacji ---
        self.HEADER_H = 64  
        self.SINGLE_OPEN = True
        self.ANIM_MS = 120      
        self.ANIM_STEPS = 8    
        
        # --- Uruchomienie budowy UI ---
        self._build_ui()
        self._apply_help_theme()

    # --- Główna metoda budująca szkielet okna (nagłówek, scroll, stopka) ---
    def _build_ui(self):
        # --- header ---
        self.header = ctk.CTkFrame(self, fg_color="transparent")
        self.header.pack(fill="x", padx=24, pady=(18, 8))
        
        self.header_title = ctk.CTkLabel(self.header, 
                                    text="Jak korzystać z aplikacji",
                                    font=ctk.CTkFont(size=20, weight="bold"),
                                    anchor="w"
                                    )
        self.header_title.pack(fill="x")
        
        self.header_subtitle = ctk.CTkLabel(self.header,
                                  text="Kliknij sekcję nagłówka, aby rozwinąć opis.",
                                  font=ctk.CTkFont(size=12),
                                  anchor="w"
                                  )
        self.header_subtitle.pack(fill="x", pady=(6, 0))
        
        self.separator = ctk.CTkFrame(self, height=1)
        self.separator.pack(fill="x", padx=24, pady=(10, 14))        
        
        # 2. Tutaj zbuduj główny kontener (ctk.CTkScrollableFrame) i przypisz go do self.scroll
        # --- scroll ---
        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True, padx=18, pady=0)        

        # 3. Wczytaj dane z pliku JSON (wykorzystaj self._load_help_sections)
        # sections = self._load_help_sections(HELP_SECTIONS_PATH)
        sections = self._load_help_sections(HELP_SECTIONS_PATH)
        
        # 4. W pętli wygeneruj sekcje na podstawie pobranych danych:
        # for sec in sections:
        #     self._add_help_section(...)
        for section in sections:
            self._add_help_section(
                title=section["title"],
                icon=section.get("icon", ""),
                color=section.get("color", "#3498DB"),
                body=section.get("body", []),
                initially_open=section.get("initially_open", False),
            )

        # --- stopka ---
        self.footer = ctk.CTkFrame(self, fg_color="transparent")
        self.footer.pack(fill="x", padx=24, pady=(10, 18))
        self.footer_lbl = ctk.CTkLabel(
            self.footer,
            text=f"Production Counter wersja programu {PROGRAM_VERSION} © {PROGRAM_YEAR} {PROGRAM_AUTHOR}",
            font=ctk.CTkFont(size=11),
            justify="center",
            anchor="w",
        )
        self.footer_lbl.pack(fill="x")


    # # # # # # # # # # # # # # # # # # # # # # # # #
    # METODY WEWNĘTRZNE (Logika i animacje)         #
    # # # # # # # # # # # # # # # # # # # # # # # # #
    
    # --- funkcja ładująca sekcje pomocy z pliku JSON (możesz ją modyfikować, np. dodając cache, obsługę błędów itp.) ---
    def _load_help_sections(self, path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            messagebox.showerror("Błąd help_sections.json", f"{type(e).__name__}: {e}\n\nPlik: {path}")
            return []

    def _add_help_section(self, title, icon, color, body, initially_open):
        """Generowanie pojedynczej rozwijanej karty"""
        # To jest najdłuższa część. Skopiuj tu logikę tworzenia "card", "header_row", "content".
        # Pamiętaj o przeniesieniu tu również zagnieżdżonych funkcji (render_body, toggle, close, open_)
        card = ctk.CTkFrame(self.scroll, fg_color=("#ffffff", "#1f1f1f"), corner_radius=14)
        card.pack(fill="x", padx=6, pady=8)

        card.pack_propagate(True)   # <-- KLUCZ: karta ma się kurczyć do zawartości

        accent = ctk.CTkFrame(card, width=4, fg_color=color, corner_radius=10)
        accent.pack(side="left", fill="y", padx=(0, 12), pady=8)

        main = ctk.CTkFrame(card, fg_color="transparent")
        main.pack(side="left", fill="both", expand=True, padx=(0, 12), pady=8)

        main.pack_propagate(True)   # <-- też ważne


        # HEADER (klikany)
        header_row = ctk.CTkFrame(main, fg_color="transparent")
        header_row.pack(fill="x")

        title_lbl = ctk.CTkLabel(
            header_row,
            text=f"{icon}  {title}",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=color,
            anchor="w",
        )
        title_lbl.pack(side="left", fill="x", expand=True)

        chev = ctk.CTkLabel(
            header_row,
            text="▼",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#cfcfcf",
            width=20,
        )
        chev.pack(side="right")

        # CONTENT (zwijany)
        content = ctk.CTkFrame(main, fg_color="transparent")
        content.pack_propagate(True)

        # ✅ trzymamy referencje do obrazów w jednym miejscu (bez img_lbl.image)
        if not hasattr(content, "_images"):
            content._images = []  # type: ignore[attr-defined]

        # funkcja renderująca treść sekcji (możesz ją modyfikować pod swoje potrzeby, np. dodając obsługę nowych typów bloków)
        def render_body(content, sec_body: list[dict]):
            # wyczyść content, gdybyś kiedyś robił re-render
            for ch in content.winfo_children():
                ch.destroy()
            content._images.clear()  # type: ignore[attr-defined]

            for block in sec_body:
                btype = block.get("type")

                if btype == "text":
                    lines = block.get("content", [])
                    if isinstance(lines, str):
                        lines = [lines]

                    lbl = ctk.CTkLabel(
                        content,
                        text="\n".join(lines),
                        font=ctk.CTkFont(size=14),
                        text_color=("#1f1f1f", "#e6e6e6"),
                        justify="left",
                        anchor="w",
                        wraplength=670,
                    )
                    lbl.pack(fill="x", pady=(8, 0), anchor="w")

                elif btype == "image":
                    fname = block.get("file", "")
                    img_path = HELP_SECTIONS_IMAGES / fname

                    if img_path.exists():
                        img = Image.open(img_path)
                        size = tuple(block.get("size", [300, 180]))
                        ctk_img = ctk.CTkImage(img, size=size)

                        img_lbl = ctk.CTkLabel(content, image=ctk_img, text="")
                        img_lbl.pack(pady=(10, 0), anchor="w")

                        # ✅ ważne: zachowaj referencję
                        content._images.append(ctk_img)  # type: ignore[attr-defined]

        # wypełnij content
        render_body(content, body)

        # funkcja licząca docelową wysokość karty po rozwinięciu (ważne dla animacji)
        def calc_open_height():
            # chwilowo pokaż content, żeby policzyć reqheight
            content.pack(fill="x")
            self.update_idletasks()

            # ile potrzeba na treść
            content_h = content.winfo_reqheight()

            # odejmij/ dodaj oddechy – dopasuj pod swój gust
            extra = 32  # paddingi karty + nagłówek itp.

            return self.HEADER_H + content_h + extra
        
        # funkcja zamykająca sekcję (zwijająca i chowająca content)
        def close():
            # jeśli już zwinięte, nic nie rób
            if content.winfo_manager() == "":
                try:
                    card.configure(height=self.HEADER_H)
                    card.pack_propagate(False)
                    chev.configure(text="▼")
                except Exception:
                    pass
                return

            try:
                chev.configure(text="▼")
            except Exception:
                pass

            # animuj wysokość w dół
            try:
                card.pack_propagate(False)
                h_now = card.winfo_height()
            except Exception:
                h_now = self.HEADER_H

            # po animacji schowaj content i odśwież scrollregion
            def after_close():
                try:
                    content.pack_forget()
                    self._refresh_scrollregion()
                except Exception:
                    pass

            self._animate_height(card, h_now, self.HEADER_H, on_done=after_close)

        # funkcja otwierająca sekcję (rozwijająca i pokazująca content, a jeśli SINGLE_OPEN=True, to też zamykająca poprzednią otwartą)
        def open_():
            # zamknij poprzednią (single-open)
            if self.SINGLE_OPEN and self.opened_content is not None and self.opened_content is not content:
                try:
                    prev_content = self.opened_content
                    prev_card = prev_content.master.master  # content -> main -> card
                    # strzałka poprzedniej
                    if self.opened_chev is not None:
                        self.opened_chev.configure(text="▼")
                    # schowaj treść poprzedniej i zjedź wysokością
                    prev_h = prev_card.winfo_height()
                    def prev_done():
                        try:
                            prev_content.pack_forget()
                        except Exception:
                            pass
                    prev_card.pack_propagate(False)
                    self._animate_height(prev_card, prev_h, self.HEADER_H, on_done=prev_done)
                except Exception:
                    pass

            # pokaż content, policz target
            try:
                card.pack_propagate(False)
                target_h = calc_open_height()
                h_now = card.winfo_height()
            except Exception:
                target_h = self.HEADER_H + 120
                h_now = self.HEADER_H

            try:
                chev.configure(text="▲")
            except Exception:
                pass

            # najpierw ustaw scroll na początek sekcji
            self._scroll_to_widget(header_row, pad=12)

            # animuj z "lockiem" do tej karty
            self._animate_height(card, h_now, target_h, lock_to=header_row)
            self.after(1, self._refresh_scrollregion)

            self.opened_content = content
            self.opened_chev = chev

            def _after_open_scroll():
                self._refresh_scrollregion()
                self._scroll_to_widget(header_row, pad=12)

            self.after(self.ANIM_MS + 30, _after_open_scroll)


        # funkcja toggle (otwórz/zamknij) – wywoływana po kliknięciu w header
        def toggle():
            is_visible = (content.winfo_manager() != "")
            if is_visible:
                # klik na już otwartą → zamknij
                close()
                if self.opened_content is content:
                    self.opened_content = None
                    self.opened_chev = None
            else:
                # klik na inną → otwórz i zamknij poprzednią
                open_()                    

        for w in (header_row, title_lbl, chev):
            w.bind("<Button-1>", lambda _e: toggle())

        if initially_open:
            open_()
        else:
            close()

    def _animate_height(self, widget, h_from, h_to, on_done=None, lock_to=None):
        """Funkcja wykonująca płynną animację"""
        # zabezpieczenie na klik spam
        if getattr(widget, "_animating", False):
            return
        widget._animating = True

        dh = (h_to - h_from) / self.ANIM_STEPS
        i = 0

        def step():
            nonlocal i
            i += 1
            h = int(h_from + dh * i)

            try:
                widget.configure(height=h)
                self._refresh_scrollregion()
                if lock_to is not None:
                    self._scroll_to_widget(lock_to, pad=12)  # trzyma nagłówek w miejscu
            except Exception:
                pass

            if i < self.ANIM_STEPS:
                widget.after(max(1, self.ANIM_MS // self.ANIM_STEPS), step)
            else:
                try:
                    widget.configure(height=h_to)
                    self._refresh_scrollregion()
                    if lock_to is not None:
                        self._scroll_to_widget(lock_to, pad=12)
                except Exception:
                    pass
                widget._animating = False
                if on_done:
                    on_done()
        step()

    def _scroll_to_widget(self, w, pad=10):
        """Przewijanie paska do otwartego widgetu"""
        try:
            self.update_idletasks()
            self.scroll.update_idletasks() # <-- Dodano odświeżanie scrolla

            canvas = getattr(self, "_parent_canvas", None) or getattr(self, "_canvas", None)
            if canvas is None:
                return

            self._refresh_scrollregion()
            self.update_idletasks()
            self.scroll.update_idletasks() # <-- Dodano odświeżanie scrolla

            bbox = canvas.bbox("all")
            if not bbox:
                return

            scroll_h = max(1, bbox[3] - bbox[1])

            # ✅ stabilne: pozycja widgetu w jednostkach canvas
            y = (w.winfo_rooty() - canvas.winfo_rooty()) + canvas.canvasy(0)
            y = max(0, int(y) - pad)

            canvas.yview_moveto(min(1.0, y / scroll_h))
        except Exception:
            pass 

    def _refresh_scrollregion(self):
        try:
            self.update_idletasks()
            canvas = getattr(self.scroll, "_parent_canvas", None) or getattr(self, "_canvas", None)
            if canvas is not None:
                canvas.configure(scrollregion=canvas.bbox("all"))
        except Exception:
            pass 

    def _apply_help_theme(self):
        """Zmiana kolorów zaleznie od trybu (Jasny/Ciemny)"""
             
        mode = ctk.get_appearance_mode()  # "Dark" / "Light"
        if mode == "Light":
            bg = "#f2f2f2"
            sep = "#d6d6d6"
            subtitle = "#555555"
            textc = "#111111"
            footer = "#666666"
            chev = "#333333"
        else:
            bg = "#151515"
            sep = "#2a2a2a"
            subtitle = "#bdbdbd"
            textc = "#ffffff"
            footer = "#8e8e8e"
            chev = "#cfcfcf"

        self.configure(fg_color=bg)

        # jeśli widgety już istnieją – odśwież je
        try:
            self.header_title.configure(text_color=textc)
            self.header_subtitle.configure(text_color=subtitle)
            self.separator.configure(fg_color=sep)
            self.footer_lbl.configure(text_color=footer)
            # strzałki w sekcjach (jeśli trzymasz referencje w liście) też możesz tu odświeżać
        except Exception:
            pass

class ReportParamsPopup(ctk.CTkToplevel):
    def __init__(self, parent, machines: list[str], on_confirm):
        super().__init__(parent)
        self.title("Parametry raportu")
        self.resizable(False, False)
        self.grab_set()
        center_popup(parent, self)
        
        # --- Czysta lista maszyn przekazana z Kontrolera ---
        self.machines = sorted({machine.strip() for machine in machines if str(machine).strip()})
        self.on_confirm = on_confirm
        
        self._build_ui()
        
    def _build_ui(self):
        ctk.CTkLabel(self, text="Wybierz maszynę (LINIA):").pack(anchor="w", padx=12, pady=(12, 4))
        self.linia_var = tk.StringVar(value=self.machines[0] if self.machines else "")
        self.linia_cb = ctk.CTkComboBox(self, values=self.machines, variable=self.linia_var, width=260)
        self.linia_cb.pack(anchor="w", padx=12, pady=(0, 10))        

        ctk.CTkLabel(self, text="Startowe zlecenie nowej grupy:").pack(anchor="w", padx=12, pady=(0, 4))
        
        vcmd = self.register(self._only_digits)

        self.start_var = tk.StringVar(value="")
        self.start_entry = ctk.CTkEntry(
            self,
            textvariable=self.start_var,
            width=260,
            validate="key",
            validatecommand=(vcmd, "%P")
        )
        self.start_entry.pack(anchor="w", padx=12, pady=(0, 12))
        self.start_entry.focus_set() 
               
        # --- Dzień danych (SAP/DB) ---
        self.day_mode_var = tk.StringVar(value="today")  # today | date
        self.day_str_var = tk.StringVar(value=date.today().isoformat())

        day_frame = ctk.CTkFrame(self, fg_color="transparent")
        day_frame.pack(fill="x", padx=12, pady=(0, 10))

        ctk.CTkLabel(day_frame, text="Dane z dnia:", width=60, anchor="w").pack(side="left")
        ctk.CTkRadioButton(day_frame, text="dziś", width=60,  variable=self.day_mode_var, value="today").pack(side="left", padx=5)
        ctk.CTkRadioButton(day_frame, text="z daty", width=60, variable=self.day_mode_var, value="date").pack(side="left", padx=5)

        day_entry = ctk.CTkEntry(day_frame, width=140, textvariable=self.day_str_var)
        day_entry.pack(side="left", padx=10)
        ctk.CTkLabel(day_frame, text="(YYYY-MM-DD)", text_color="#aaaaaa").pack(side="left") 
               
        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=12, pady=(0, 12))

        ctk.CTkButton(btns, text="Anuluj", command=self.destroy).pack(side="right", padx=(8, 0))
        ctk.CTkButton(btns, text="OK", command=self._on_ok).pack(side="right")

    def _on_ok(self):
        linia = (self.linia_var.get() or "").strip().upper()
        start_order_id = (self.start_var.get() or "").strip()

        if not start_order_id:
            messagebox.showwarning("Brak zlecenia", "Podaj startowe zlecenie.")
            return

        if not start_order_id.isdigit():
            messagebox.showwarning(
                "Błędna wartość",
                "Startowe zlecenie musi składać się wyłącznie z cyfr."
            )
            return
        
        # --- parsowanie dnia ---
        mode = self.day_mode_var.get()
        ds = (self.day_str_var.get() or "").strip()

        if mode == "date":
            try:
                day_value = datetime.strptime(ds, "%Y-%m-%d").date()
            except ValueError:
                messagebox.showerror("Błąd daty", "Podaj datę w formacie YYYY-MM-DD.")
                return
        else:
            day_value = date.today()

        result = {"linia": linia, "start_order_id": start_order_id, "day": day_value}            

        self.on_confirm(result)
        self.destroy()
    
    def _only_digits(self, new_value: str) -> bool:
        # pozwalamy na pusty (user jeszcze pisze)
        return new_value.isdigit() or new_value == ""    
    
class SchedulePopup(ctk.CTkToplevel):
    def __init__(self, parent, on_confirm):
        super().__init__(parent)
        self.title("Parametry liczenia grupy - harmonogram")
        self.resizable(False, False)
        self.grab_set()
        
        # -- Przechowujemy callback do potwierdzenia, który zostanie wywołany z wynikiem po kliknięciu OK ---
        self.on_confirm = on_confirm
   
        # -- zmiene dla trzymania stanu wyboru (zmiana, tryb startu, data startu) ---
        self.shift_var = tk.IntVar(value=1)
        self.start_mode_var = tk.StringVar(value="today")
        self.start_day_var = tk.StringVar(value=date.today().isoformat())
        
        self._build_ui()
        center_popup(parent, self)
        
    def _build_ui(self):
        # --- WIERSZ 1: Zmiana ---
        shift_frame = ctk.CTkFrame(self, fg_color="transparent")
        shift_frame.pack(fill="x", padx=20, pady=(20, 10))
        
        ctk.CTkLabel(shift_frame, text="Start od zmiany:", width=120, anchor="w").pack(side="left")
        ctk.CTkRadioButton(shift_frame, text="1", variable=self.shift_var, value=1).pack(side="left", padx=10)
        ctk.CTkRadioButton(shift_frame, text="2", variable=self.shift_var, value=2).pack(side="left", padx=10)
        ctk.CTkRadioButton(shift_frame, text="3", variable=self.shift_var, value=3).pack(side="left", padx=10)
        
        # --- WIERSZ 2: Tryb startu (dziś/data) ---
        mode_frame = ctk.CTkFrame(self, fg_color="transparent")
        mode_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(mode_frame, text="Start liczenia:", width=120, anchor="w").pack(side="left")
        ctk.CTkRadioButton(mode_frame, text="od dziś", variable=self.start_mode_var, value="today").pack(side="left", padx=10)
        ctk.CTkRadioButton(mode_frame, text="od daty", variable=self.start_mode_var, value="date").pack(side="left", padx=10)
        
        # --- WIERSZ 3: Pole daty ---
        date_frame = ctk.CTkFrame(self, fg_color="transparent")
        date_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(date_frame, text="Podaj datę:", width=120, anchor="w").pack(side="left")
        self.date_entry = ctk.CTkEntry(date_frame, width=140, textvariable=self.start_day_var)
        self.date_entry.pack(side="left", padx=10)
        ctk.CTkLabel(date_frame, text="(YYYY-MM-DD)", text_color="#aaaaaa").pack(side="left")
        
        # --- WIERSZ 4: Przyciski ---
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(10, 20))
        
        ctk.CTkButton(btn_frame, text="Anuluj", command=self.destroy, width=100).pack(side="right", padx=(10, 0))
        ctk.CTkButton(btn_frame, text="OK", command=self._on_ok, width=100).pack(side="right")

    def _on_ok(self):
        mode = self.start_mode_var.get()
        ds = self.start_day_var.get().strip()

        # --- walidacja daty ---
        if mode == "date":
            try:
                datetime.strptime(ds, "%Y-%m-%d")
            except ValueError:
                messagebox.showerror("Błąd daty", "Podaj datę w formacie YYYY-MM-DD.")
                return

        # --- przygotowanie wyniku ---
        result = {
            "start_shift": self.shift_var.get(),
            "start_mode": mode,
            "start_date": ds
        }
        
        # --- wywołanie callbacka (przekazanie wyniku do kontrolera) ---
        self.on_confirm(result)
        self.destroy()
        
class OrderIdPopup(ctk.CTkToplevel):
    def __init__(self, parent, on_confirm):
        super().__init__(parent)
        self.title("Potwierdź termin zlecenia")
        self.resizable(False, False)
        self.grab_set()
        self.on_confirm = on_confirm
        
        self._build_ui()
        center_popup(parent, self)

    def _build_ui(self):
        ctk.CTkLabel(self, text="Znajdź zlecenie aby sprawdzić datę zakończenia:").pack(padx=12, pady=(12, 6))
        
        vcmd = (self.register(self._only_digits), "%P")        
        self.v = tk.StringVar(value="")
        entry = ctk.CTkEntry(self, textvariable=self.v, width=320, validate="key", validatecommand=vcmd)
        entry.pack(padx=12, pady=(0, 10))
        entry.focus_set()

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=12, pady=(0, 12))
        ctk.CTkButton(btns, text="Anuluj", command=self.destroy).pack(side="right", padx=(8, 0))
        ctk.CTkButton(btns, text="OK", command=self._on_ok).pack(side="right")

    def _only_digits(self, new_value: str) -> bool:
        return new_value.isdigit() or new_value == ""

    def _on_ok(self):
        val = (self.v.get() or "").strip()
        if not val:
            messagebox.showwarning("Brak zlecenia", "Wpisz numer zlecenia.")
            return
        if not val.isdigit():
            messagebox.showwarning("Błąd", "Zlecenie musi składać się z cyfr.")
            return
        self.on_confirm(val)
        self.destroy()


class CalcModePopup(ctk.CTkToplevel):
    def __init__(self, parent, workplace: str, default_speed: float, default_pieces_per_shift: int, on_confirm):
        super().__init__(parent)
        self.title("Parametry przeliczenia produkcji")
        self.grab_set()
        self.on_confirm = on_confirm
        
        self.workplace = workplace
        self.default_speed = default_speed
        self.default_pieces_per_shift = default_pieces_per_shift
        
        self.calendar_var = tk.StringVar(value="workdays")
        self.start_shift_var = tk.IntVar(value=1) 
        self.start_mode_var = tk.StringVar(value="today")
        self.start_date_var = tk.StringVar(value=date.today().isoformat())
        self.mode_var = tk.StringVar(value="shift")
        
        self._build_ui()
        center_popup(parent, self)

    def _build_ui(self):
        ctk.CTkLabel(self, text=f"Stanowisko: {self.workplace}", font=ctk.CTkFont(size=16, weight="bold")).pack(padx=16, pady=(14, 6), anchor="w")

        frame = ctk.CTkFrame(self)
        frame.pack(fill="both", expand=True, padx=16, pady=10)

        row1 = ctk.CTkFrame(frame)
        row1.pack(fill="x", padx=10, pady=(10, 6))
        
        row2 = ctk.CTkFrame(frame)
        row2.pack(fill="x", padx=10, pady=6)
                
        spacer = ctk.CTkFrame(frame, height=12, fg_color="transparent")
        spacer.pack(fill="x")

        row_cal = ctk.CTkFrame(frame)
        row_cal.pack(fill="x", padx=10, pady=(20, 6))
        
        row_start = ctk.CTkFrame(frame)
        row_start.pack(fill="x", padx=10, pady=6)
        
        row_startdate = ctk.CTkFrame(frame)
        row_startdate.pack(fill="x", padx=10, pady=6)
        
        # --- Start daty ---
        ctk.CTkLabel(row_startdate, text="Start liczenia:").pack(side="left")
        ctk.CTkRadioButton(row_startdate, text="od dziś", variable=self.start_mode_var, value="today").pack(side="left", padx=10)
        ctk.CTkRadioButton(row_startdate, text="od daty", variable=self.start_mode_var, value="date").pack(side="left", padx=10)
        
        self.date_entry = ctk.CTkEntry(row_startdate, width=130, textvariable=self.start_date_var)
        self.date_entry.pack(side="left", padx=10)
        ctk.CTkLabel(row_startdate, text="(YYYY-MM-DD)", text_color="#aaaaaa").pack(side="left")        
        
        # --- Tryby ---
        ctk.CTkRadioButton(row2, text="Przelicz przez szt./zmianę:", variable=self.mode_var, value="shift").pack(side="left")
        self.pshift_var = tk.StringVar(value=str(self.default_pieces_per_shift))
        ctk.CTkEntry(row2, width=120, textvariable=self.pshift_var).pack(side="left", padx=10)
        
        ctk.CTkRadioButton(row1, text="Przelicz przez prędkość (m/min):", variable=self.mode_var, value="speed").pack(side="left")
        self.speed_var = tk.StringVar(value=str(self.default_speed))
        ctk.CTkEntry(row1, width=120, textvariable=self.speed_var).pack(side="left", padx=10)

        # --- Zmiana i Kalendarz ---
        ctk.CTkLabel(row_start, text="Start od zmiany:").pack(side="left")
        for val in [1, 2, 3]:
            ctk.CTkRadioButton(row_start, text=str(val), variable=self.start_shift_var, value=val).pack(side="left", padx=10)

        ctk.CTkLabel(row_cal, text="Kalendarz:").pack(side="left")
        ctk.CTkRadioButton(row_cal, text="dni robocze", variable=self.calendar_var, value="workdays").pack(side="left", padx=10)
        ctk.CTkRadioButton(row_cal, text="dni robocze + weekendy", variable=self.calendar_var, value="all").pack(side="left", padx=10)
        
        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=16, pady=14)
        ctk.CTkButton(btns, text="Anuluj", command=self.destroy).pack(side="right")
        ctk.CTkButton(btns, text="OK", command=self._on_ok).pack(side="right", padx=10)

    def _parse_float(self, s: str) -> float:
        return float(s.replace(",", ".").strip())

    def _on_ok(self):
        try:
            result = {}
            if self.mode_var.get() == "speed":
                v = self._parse_float(self.speed_var.get())
                if v <= 0: raise ValueError("Prędkość musi być > 0.")
                result = {"mode": "speed", "speed_m_per_min": v}
            else:
                v = int(self._parse_float(self.pshift_var.get()))
                if v <= 0: raise ValueError("Sztuki na zmianę muszą być > 0.")
                result = {"mode": "shift", "pieces_per_shift": v}
                
            result.update({
                "calendar": self.calendar_var.get(),
                "start_shift": int(self.start_shift_var.get()),
                "start_mode": self.start_mode_var.get(),
                "start_date": self.start_date_var.get()
            })
        except Exception as e:
            messagebox.showerror("Błędna wartość", str(e))
            return
        
        self.on_confirm(result)
        self.destroy()