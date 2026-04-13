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
        
    def run_matching(self) -> dict:
        # 1. Walidacja stron 0022 (szukamy braków)
        self._validate_double_sided_orders()
        
        # 2. Budowa bloków z Hydry
        self._build_blocks()
        
        # 3. Liczenie wymaganych metrów dla każdego bloku na podstawie planu
        return {
            "blocks_count": len(self.blocks),
            "missing_articles": self.missing_0022_articles
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