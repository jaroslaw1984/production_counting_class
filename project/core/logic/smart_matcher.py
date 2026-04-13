import pandas as pd
import re
from collections import Counter, defaultdict

class SmartPlanMatcher:
    # Wzorce artykułów, dla których brak strony 0022 jest poprawny (ignorujemy je)
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
        
        # Na razie zwracamy testowy słownik, żeby nie powodować błędów,
        # dopóki nie napiszemy reszty metod.
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

        # Interesują nas tylko 0021 i 0022
        tmp = tmp[tmp["side"].isin({"0021", "0022"})].copy()
        if tmp.empty:
            return

        sides_by_article = tmp.groupby("article")["side"].apply(lambda s: set(s.tolist()))

        for article, sides in sides_by_article.items():
            a = str(article)

            # IGNORUJ artykuły, które z definicji nie mają 0022
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