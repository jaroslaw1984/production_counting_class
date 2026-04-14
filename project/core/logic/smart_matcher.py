import pandas as pd
import re
from collections import Counter, defaultdict

class SmartPlanMatcher:
    # --- wzorce artykułów, dla których brak strony 0022 jest poprawny (ignorujemy je) ---
    ONLY_0021_PATTERNS = [
        r"-[123]00",  # np. -100..., -200..., -300... => tylko 0021
    ]

    def __init__(self, df_hydra_group: pd.DataFrame, df_smart_plan: pd.DataFrame | None, df_sap: pd.DataFrame):
        self.df_hydra = df_hydra_group
        self.df_plan = df_smart_plan
        self.df_sap = df_sap
        
        self.use_smart_matching = isinstance(self.df_plan, pd.DataFrame) and not self.df_plan.empty
        
        self.blocks = []
        self.required_by_block = {}
        self.sap_rows_by_index = {}
        self.allocated_items = {}
        self.missing_0022_articles = []
        
        self.sap_user = ""
        self.sap_date = ""
        
    def run_matching(self) -> dict:
            """
            Główny silnik. Odpala po kolei kroki algorytmu.
            Zwraca słownik z gotowymi danymi dla kontrolera.
            """
            # 1. Walidacja stron 0022 (szukamy braków)
            self._validate_double_sided_orders()
            
            # 2. Budowa bloków z Hydry
            self._build_blocks()
            
            # 3. Jeśli mamy plan, liczymy metry z planu
            if self.use_smart_matching:
                self._calc_required_m()
                
            # 4. Przygotowanie danych z SAP
            self._prepare_sap_data()
                
            # 5. Główna alokacja / Dobieranie pozycji (SAP -> Hydra)
            lines, rows = self._allocate_sap_items()
            
            # Zwracamy czysty wynik do Kontrolera
            return {
                "blocks": self.blocks,
                "lines": lines,
                "rows": rows,
                "missing_articles": self.missing_0022_articles,
                "sap_user": self.sap_user,
                "sap_date": self.sap_date  
            }

    # # # # # # # # # #
    # METODY PRYWATNE #
    # # # # # # # # # # 

    def _validate_double_sided_orders(self) -> None:
        """
        Sprawdza, czy jeśli artykuł ma stronę 0021, to czy ma też 0022.
        Wynik zapisuje w self.missing_0022_articles.
        """
        if self.df_hydra is None or self.df_hydra.empty or "article" not in self.df_hydra.columns:
            return

        tmp = self.df_hydra.copy()
        tmp["article"] = tmp["article"].astype("string").str.strip()
        tmp["side"] = (
            tmp["side"].astype("string").str.strip()
            .str.replace(r"\.0$", "", regex=True)
            .str.zfill(4)
        )

        # --- interesują nas tylko 0021 i 0022 ---
        tmp = tmp[tmp["side"].isin({"0021", "0022"})].copy()
        if tmp.empty:
            return

        sides_by_article = tmp.groupby("article")["side"].apply(lambda s: set(s.tolist()))

        for article, sides in sides_by_article.items():
            a = str(article)

            # --- IGNORUJ artykuły, które z definicji nie mają 0022 ---
            if any(re.search(pat, a) for pat in self.ONLY_0021_PATTERNS):
                continue

            # Jeśli jest 0021, a nie ma 0022 => dopisujemy do listy błędów
            if "0021" in sides and "0022" not in sides:
                self.missing_0022_articles.append(a)

    def _normalize_order_id_series(self, s: pd.Series) -> pd.Series:
        """Narzędzie pomocnicze do czyszczenia numerów zleceń."""
        s = s.astype("string").str.strip()
        s = s.str.replace(r"\.0$", "", regex=True)

        mask = s.str.fullmatch(r"\d+").fillna(False) & (s.str.len() < 12)
        s.loc[mask] = s.loc[mask].str.zfill(12)
        return s

    def _build_blocks(self) -> None:
        """
        Grupuje ciągłe zlecenia o tym samym grundprofil i side w bloki.
        Zapisuje gotową listę bloków w self.blocks.
        """
        tmp = self.df_hydra.copy()
        tmp["grundprofil"] = tmp["grundprofil"].astype("string").str.strip()
        tmp["side"] = tmp["side"].astype("string").str.strip().str.zfill(4)
        tmp["order_id"] = self._normalize_order_id_series(tmp["order_id"])

        blocks = []
        prev = None
        start = 0

        keys = list(zip(tmp["grundprofil"].tolist(), tmp["side"].tolist()))

        for i, key in enumerate(keys):
            if key != prev:
                if prev is not None:
                    b = tmp.iloc[start:i]
                    blocks.append({
                        "gp": prev[0],
                        "side": prev[1],
                        "order_ids": set(b["order_id"].tolist()),
                        "start_i": start,
                        "end_i": i - 1,
                    })
                prev = key
                start = i

        if prev is not None and len(tmp) > 0:
            b = tmp.iloc[start:]
            blocks.append({
                "gp": prev[0],
                "side": prev[1],
                "order_ids": set(b["order_id"].tolist()),
                "start_i": start,
                "end_i": len(tmp) - 1,
            })
            
        self.blocks = blocks
        
    def _calc_required_m(self) -> None:
        """
        Liczy metry do zrobienia dla każdego bloku z Hydry na podstawie wczytanego planu.
        Wynik zapisuje w self.required_by_block.
        """
        # --- jeśli nie ma planu, po prostu pomijamy ten krok ---
        if not self.use_smart_matching or self.df_plan is None or self.df_plan.empty:
            return

        dfx = self.df_plan.copy()

        profile_col = "profile_full" if "profile_full" in dfx.columns else "profile"

        # --- baza profilu z planu (np. "HO8030") ---
        dfx["index_base"] = (
            dfx[profile_col]
            .astype("string")
            .str.strip()
            .str.split("-", n=1)
            .str[0]
        )

        dfx["order_id"] = self._normalize_order_id_series(dfx["order_id"])

        # --- normalizujemy stronę w planie produkcji ---
        if "side" in dfx.columns:
            dfx["side_norm"] = (
                dfx["side"].astype("string").str.strip()
                .str.replace(r"\.0$", "", regex=True)
                .str.zfill(4)
            )
        else:
            dfx["side_norm"] = "0021"

        target_p = pd.to_numeric(dfx["target_value_p"], errors="coerce").fillna(0.0)

        if "good_qty_p" in dfx.columns:
            good_p = pd.to_numeric(dfx["good_qty_p"], errors="coerce").fillna(0.0)
        else:
            good_p = pd.Series(0.0, index=dfx.index)

        unit = dfx["unit_p"].astype("string").str.strip().str.upper()

        # --- liczenie brakującej produkcji ---
        remaining_p = target_p.copy()
        mask_started = good_p > 0
        remaining_p.loc[mask_started] = (target_p - good_p).clip(lower=0.0)

        # --- upewniamy się, że to metry ---
        dfx["_m"] = remaining_p.where(unit == "M", 0.0)

        out = {}

        for i, b in enumerate(self.blocks):
            gp = str(b["gp"]).strip()
            gp_base = gp.split("-", 1)[0]
            orders = b.get("order_ids") or set()
            b_side = str(b.get("side", "")).strip().zfill(4)

            if not orders:
                out[i] = 0.0
                continue

            # --- twardo filtrowanie po bazie, zleceniach i stronie ---
            m = dfx.loc[
                (dfx["index_base"] == gp_base) & 
                (dfx["order_id"].isin(orders)) &
                (dfx["side_norm"] == b_side),
                "_m"
            ].sum()

            out[i] = float(m)

        self.required_by_block = out

    def _prepare_sap_data(self) -> None:
        """
        Przetwarza surowy DataFrame z SAP (self.df_sap) na czysty, zoptymalizowany pod algorytm słownik.
        Wynik zapisuje w self.sap_rows_by_index.
        """
        if self.df_sap is None or self.df_sap.empty:
            return

        sap_rows: dict[str, list[dict]] = {}

        for _, r in self.df_sap.iterrows():
            idx = str(r.get("INDEKS", "")).strip()
            if not idx:
                continue
                
            # --- wyciąganie użytkownika i daty z pierwszego napotkanego wiersza ---
            if not self.sap_user and "USER" in self.df_sap.columns:
                u = r.get("USER")
                if pd.notna(u) and str(u).strip():
                    self.sap_user = str(u).strip()
                    
            if not self.sap_date and "DATA" in self.df_sap.columns:
                d = r.get("DATA")
                if pd.notna(d) and str(d).strip():
                    self.sap_date = str(d).strip()

            # --- parsowanie ilości (ochrona przed przecinkami i NaN) ---
            qty = r.get("ILOSC", 0)
            if isinstance(qty, str):
                qty = qty.replace(",", ".")
            try:
                qty = float(qty)
            except Exception:
                qty = 0.0

            # --- parsowanie sztuk ---
            szt = r.get("IL_SZT", 0)
            try:
                szt = int(szt)
            except Exception:
                szt = 0

            # --- jednostka ---
            jm = str(r.get("JM", "M")).strip()

            # --- detekcja sekwencji (Sequenz) - z szukaniem różnych wariantów nazwy kolumny ---
            seq = None
            for cand in ("Sequenz", "sequenz", "sequence", "Sequance", "Sequenc", "sequenc"):
                if cand in self.df_sap.columns:
                    seq_raw = r.get(cand)
                    try:
                        if seq_raw is not None:
                            seq = int(float(str(seq_raw).replace(",", ".")))
                    except Exception:
                        pass
                    break

            # --- dodajemy gotowy, sformatowany słownik dla danego indeksu ---
            sap_rows.setdefault(idx, []).append({
                "qty": qty,
                "szt": szt,
                "jm": jm,
                "seq": seq,
            })

        self.sap_rows_by_index = sap_rows
        
    def _pick_item_without_required(self, items: list[dict], remaining_occurrences: int) -> dict:
            """
            Fallback kiedy nie mamy required_m:
            Dobiera pozycję najbliższą średniej ilości na pozostały blok.
            """
            if not items:
                return {}

            remaining_occurrences = max(int(remaining_occurrences), 1)
            total_left = sum(float(it.get("qty", 0.0) or 0.0) for it in items)
            avg = total_left / remaining_occurrences

            def q(it):
                return float(it.get("qty", 0.0) or 0.0)

            if remaining_occurrences > 1:
                best = max(items, key=lambda it: q(it))
            else:
                best = min(items, key=lambda it: (abs(q(it) - avg), -q(it)))
                
            items.remove(best)
            return best

    def _pick_items_best_fit(
        self, items: list[dict], required_m: float, 
        max_over_ratio: float = 3.0, rel_tol: float = 0.20, abs_tol: float = 10.0
    ) -> list[dict]:
        """
        Dobiera pozycje z SAP dla konkretnego wymaganego metrażu.
        """
        if not items:
            return []
        req = float(required_m or 0.0)
        if req <= 0:
            return []

        def q(it): 
            return float(it.get("qty", 0.0) or 0.0)

        bigger = [it for it in items if q(it) >= req]
        if bigger:
            reasonable = [it for it in bigger if q(it) <= req * max_over_ratio]
            candidates = reasonable if reasonable else bigger

            tol = max(req * rel_tol, abs_tol)
            near = [it for it in candidates if (q(it) - req) <= tol]

            best_pool = near if near else candidates
            best = min(best_pool, key=lambda it: (q(it) - req, q(it)))
            items.remove(best)
            return [best]

        picked = []
        total = 0.0
        for it in sorted(items, key=q, reverse=True):
            picked.append(it)
            total += q(it)
            items.remove(it)
            if total >= req:
                break
        return picked

    def _pre_allocate_fallback(self) -> None:
        """
        Przydziela pozycje z SAP do bloków Hydry z pominięciem Smart Matchingu,
        opierając się na sekwencji (Sequenz) lub sortowaniu malejącym.
        """
        if self.use_smart_matching:
            return

        block_indices_by_gp = defaultdict(list)
        for block_no, b in enumerate(self.blocks):
            key = (b["gp"], b["side"])
            block_indices_by_gp[key].append(block_no)

        for (gp, side), block_nos in block_indices_by_gp.items():
            if len(block_nos) > 1:
                items = self.sap_rows_by_index.get(gp, [])
                if not items:
                    continue
                has_seq = any(it.get("seq") is not None for it in items)
                
                if has_seq:
                    items_sorted = sorted(items, key=lambda it: (it.get("seq") or 0))
                    for bn, sap_item in zip(block_nos, items_sorted):
                        self.allocated_items[bn] = sap_item
                        if sap_item in self.sap_rows_by_index.get(gp, []):
                            self.sap_rows_by_index[gp].remove(sap_item)
                else:
                    items_sorted = sorted(items, key=lambda it: float(it.get("qty", 0.0) or 0.0), reverse=True)
                    for bn, sap_item in zip(reversed(block_nos), items_sorted):
                        self.allocated_items[bn] = sap_item
                        if sap_item in self.sap_rows_by_index.get(gp, []):
                            self.sap_rows_by_index[gp].remove(sap_item)

    def _allocate_sap_items(self) -> tuple[list[str], list[dict]]:
        """
        Główna pętla przydzielająca. Łączy zebrane wcześniej dane.
        Zwraca gotowe linie do podglądu tekstowego oraz słowniki (wiersze) do DOCX.
        """
        # --- najpierw spróbujmy pre-alokacji (zadziała tylko gdy nie ma Smart Matchingu) --- 
        self._pre_allocate_fallback()

        rows = []
        lp = 1
        
        total_blocks_by_gp = Counter(b["gp"] for b in self.blocks)
        used_blocks_by_gp = defaultdict(int)

        for block_no, b in enumerate(self.blocks):
            gp = b["gp"]
            items = self.sap_rows_by_index.get(gp, [])
            items.sort(key=lambda it: float(it.get("qty", 0.0) or 0.0))

            required_m = self.required_by_block.get(block_no)
            total_qty = 0.0
            total_szt = 0
            jm = "M"

            # --- sprawdzamy czy blok dostał już przypisanie w fallbacku ---
            if block_no in self.allocated_items:
                picked_item = self.allocated_items[block_no]
                total_qty = float(picked_item.get("qty", 0.0) or 0.0)
                total_szt = int(picked_item.get("szt", 0) or 0)
                jm = picked_item.get("jm", "M")
            else:
                if not items:
                    continue
                jm = items[0]["jm"] if items else "M"

                if required_m is not None and required_m > 0:
                    # Smart Matching
                    picked = self._pick_items_best_fit(items, required_m, max_over_ratio=3.0, rel_tol=0.25, abs_tol=15.0)
                    for it in picked:
                        total_qty += float(it.get("qty", 0.0))
                        total_szt += int(it.get("szt", 0))
                else:
                    # --- fallback (kiedy required_m jest None lub 0) ---
                    remaining_occ = total_blocks_by_gp[gp] - used_blocks_by_gp[gp]
                    it = self._pick_item_without_required(items, remaining_occ)
                    if not it:
                        continue
                    total_qty += float(it.get("qty", 0.0))
                    total_szt += int(it.get("szt", 0))

            rows.append({
                "lp": lp,
                "index": gp,
                "qty": float(total_qty),
                "jm": jm,
                "szt": int(total_szt),
                "pallets": "",
            })

            used_blocks_by_gp[gp] += 1
            lp += 1

        # --- DOMKNIĘCIE: resztki SAP dla indeksów, które zostały niewykorzystane ---
        for idx, leftovers in self.sap_rows_by_index.items():
            if not leftovers:
                continue

            extra_qty = sum(float(it.get("qty", 0.0) or 0.0) for it in leftovers)
            extra_szt = sum(int(it.get("szt", 0) or 0) for it in leftovers)

            if extra_qty <= 0 and extra_szt <= 0:
                continue

            # --- znajdź ostatni wiersz tego indeksu w raporcie ---
            last_pos = None
            for i in range(len(rows) - 1, -1, -1):
                if rows[i]["index"] == idx:
                    last_pos = i
                    break

            if last_pos is not None:
                rows[last_pos]["qty"] += extra_qty
                rows[last_pos]["szt"] += extra_szt

            leftovers.clear()

        # --- budowa stringów na potrzeby podglądu ---
        lines = []
        for r in rows:
            lines.append(f'{r["lp"]:>2}. {r["index"]:<18}  {float(r["qty"]):>10.1f} {r["jm"]:<2}  {int(r["szt"]):>6}')

        return lines, rows