from __future__ import annotations
from pathlib import Path
import pandas as pd

# DB loader:
# jeśli masz inaczej ustawione importy, dopasuj ścieżkę importu
from project.config.count_per_loader import fetch_workplace_config, fetch_profiles_config


def _project_dir() -> Path:
    # workplace_config_provider.py jest w project/config/
    return Path(__file__).resolve().parents[1]  # -> project/

def _load_csv_config() -> pd.DataFrame:
    cfg_path = _project_dir() / "config" / "machine_config.csv"
    df = pd.read_csv(cfg_path, sep=";")

    # Ujednolicenie nazw kolumn (na wypadek wariantów w CSV)
    # Dostosuj jeśli Twoje CSV ma inne nazwy.
    rename_map = {}
    if "worklpace" in df.columns and "workplace" not in df.columns:
        rename_map["worklpace"] = "workplace"
    df = df.rename(columns=rename_map)

    # Normalizacja typów
    df["workplace"] = df["workplace"].astype(str).str.strip()
    df["speed_m_per_min"] = pd.to_numeric(df["speed_m_per_min"], errors="coerce")
    df["count_by_shift"] = pd.to_numeric(df["count_by_shift"], errors="coerce")
    return df


def _normalize_db_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["workplace"] = df["workplace"].astype(str).str.strip()
    df["speed_m_per_min"] = pd.to_numeric(df["speed_m_per_min"], errors="coerce")
    df["count_by_shift"] = pd.to_numeric(df["count_by_shift"], errors="coerce")
    return df


def merge_db_and_csv_config(sync_missing_to_db: bool = False) -> tuple[pd.DataFrame, str, list[str]]:
    """
    Zwraca:
      (df_merged, source, missing_in_db)

    - df_merged: kompletna konfiguracja (DB ma priorytet, CSV domyka braki)
    - source: "db", "csv", albo "db+csv"
    - missing_in_db: lista workplace, których nie było w DB (wzięte z CSV)
    """

    # CSV zawsze mamy jako fallback
    df_csv = _load_csv_config()

    # Spróbuj DB
    try:
        df_db = fetch_workplace_config()
        df_db = _normalize_db_df(df_db)
    except Exception:
        # DB padło → jedziemy tylko na CSV
        return df_csv, "csv", []

    if df_db.empty:
        return df_csv, "csv", list(df_csv["workplace"].unique())

    db_set = set(df_db["workplace"].unique())
    csv_set = set(df_csv["workplace"].unique())
    missing_in_db = sorted(csv_set - db_set)

    # DB ma pierwszeństwo: bierzemy wszystko z DB + dopisujemy brakujące z CSV
    df_missing = df_csv[df_csv["workplace"].isin(missing_in_db)].copy()
    df_merged = pd.concat([df_db, df_missing], ignore_index=True)

    source = "db" if not missing_in_db else "db+csv"

    # Opcjonalna synchronizacja braków do DB (tylko dopisanie nowych maszyn)
    if sync_missing_to_db and missing_in_db:
        # Import lokalny, żeby nie było zależności gdy ktoś nie ma uprawnień
        from project.config.count_per_loader import insert_missing_workplaces  # dopiszemy niżej
        insert_missing_workplaces(df_missing)

    return df_merged, source, missing_in_db

def _load_csv_profiles() -> pd.DataFrame:
    """Wczytuje lokalny plik z profilami jako awaryjny fallback."""
    cfg_path = _project_dir() / "config" / "profile_config.csv"
    if not cfg_path.exists():
        # Zabezpieczenie, gdyby ktoś przypadkiem usunął plik CSV
        return pd.DataFrame(columns=["profile", "side", "setting_time"])
        
    df = pd.read_csv(cfg_path, sep=";")
    
    # Normalizacja typów
    df["profile"] = df["profile"].astype(str).str.strip()
    df["side"] = df["side"].astype(str).str.strip()
    # Wymuszamy liczby całkowite dla czasu zbrojenia
    df["setting_time"] = pd.to_numeric(df["setting_time"], errors="coerce").fillna(0).astype(int)
    return df

def _normalize_profiles_db_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["profile"] = df["profile"].astype(str).str.strip()
    df["side"] = df["side"].astype(str).str.strip()
    df["setting_time"] = pd.to_numeric(df["setting_time"], errors="coerce").fillna(0).astype(int)
    return df

def merge_db_and_csv_profiles() -> tuple[pd.DataFrame, str]:
    """
    Szybka wersja: Odpytuje bazę danych. 
    Jeśli baza odpowiada, zwraca dane od razu. W przeciwnym razie ładuje CSV.
    Nie porównuje już różnic, aby nie obciążać interfejsu.
    """
    try:
        df_db = fetch_profiles_config()
        if not df_db.empty:
            return _normalize_profiles_db_df(df_db), "db"
    except Exception as e:
        print(f"Odczyt DB dla profili nie powiódł się (fallback na CSV): {e}")
        
    # Jeśli DB zawiedzie lub jest puste, po prostu ładujemy CSV
    df_csv = _load_csv_profiles()
    return df_csv, "csv"
