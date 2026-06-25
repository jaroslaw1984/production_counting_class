import pandas as pd
import pyodbc
import urllib.parse
from typing import cast
from sqlalchemy import create_engine
from project.config.paths import PROFILES_TABLE

PLAN_SERVER = "kronos.sip.local"
PLAN_DB = "Raporty"
PLAN_TABLE = "dbo.tblPlanowanieWorkplaces"
SAP_TABLE = "dbo.HANA_ZMDRS_RAPORT"   # <- jeśli to view, też OK

def _pick_driver() -> str:
    drivers = pyodbc.drivers()
    for name in ("ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server", "SQL Server"):
        if name in drivers:
            return name
    raise RuntimeError(f"No SQL Server ODBC driver found. Available: {drivers}")

def _get_plan_engine():
    driver = _pick_driver()
    conn_str = (
        f"DRIVER={{{driver}}};"
        f"SERVER={PLAN_SERVER};"
        f"DATABASE={PLAN_DB};"
        "Trusted_Connection=yes;"
        "Encrypt=yes;"
        "TrustServerCertificate=yes;"
    )
    quoted_conn_str = urllib.parse.quote_plus(conn_str)
    # Tworzymy silnik z wbudowaną optymalizacją dla wielu rekordów!
    return create_engine(f"mssql+pyodbc:///?odbc_connect={quoted_conn_str}", fast_executemany=True)

def fetch_workplace_config() -> pd.DataFrame:
    sql = f"SELECT workplace, speed_m_per_min, count_by_shift FROM {PLAN_TABLE}"
    engine = _get_plan_engine()
    
    # --- # Pandas woli dostać po prostu engine. Sam zarządza otwarciem i zamknięciem. ---
    df = pd.read_sql(sql, engine)
    return df

def insert_missing_workplaces(df_missing: pd.DataFrame) -> None:
    """
    Dopisuje brakujące workplace do tabeli (tylko INSERT).
    df_missing musi mieć kolumny: workplace, speed_m_per_min, count_by_shift
    """
    if df_missing is None or df_missing.empty:
        return

    sql = f"""
        INSERT INTO {PLAN_TABLE} (workplace, speed_m_per_min, count_by_shift)
        VALUES (?, ?, ?)
    """

    rows = []
    for _, r in df_missing.iterrows():
        wp = str(r["workplace"]).strip()
        sp = float(r["speed_m_per_min"]) if pd.notna(r["speed_m_per_min"]) else None
        cb = int(r["count_by_shift"]) if pd.notna(r["count_by_shift"]) else None
        rows.append((wp, sp, cb))

    engine = _get_plan_engine()
    with engine.raw_connection() as conn:
        cur = conn.cursor()
        cur.executemany(sql, rows)
        conn.commit()
        
def update_count_by_shift(workplace: str, count_by_shift: int) -> None:
    sql = f"UPDATE {PLAN_TABLE} SET count_by_shift = ? WHERE workplace = ?"
    engine = _get_plan_engine()
    with engine.raw_connection() as conn:
        cur = conn.cursor()
        cur.execute(sql, (int(count_by_shift), str(workplace).strip()))
        conn.commit()

def update_speed(workplace: str, speed_m_per_min: float) -> None:
    sql = f"UPDATE {PLAN_TABLE} SET speed_m_per_min = ? WHERE workplace = ?"
    engine = _get_plan_engine()
    with engine.raw_connection() as conn:
        cur = conn.cursor()
        cur.execute(sql, (float(speed_m_per_min), str(workplace).strip()))
        conn.commit()
        
# --- project/config/count_per_loader.py ---
def fetch_sap_basic_profiles(linia: str, day) -> pd.DataFrame:
    """
    Zwraca dane SAP dla danej linii i dnia.
    Kolumny wejściowe: INDEKS, ILOSC, JM, IL_SZT, LINIA, DATA, USER
    """
    sql = f"""
        SELECT INDEKS, ILOSC, JM, IL_SZT, LINIA, DATA, [USER]
        FROM {SAP_TABLE}
        WHERE LINIA = ?
          AND CAST(DATA as date) = CAST(? as date)
    """
    # --- Pandas dzięki temu użyje SQLAlchemy do zapytania. ---
    engine = _get_plan_engine()
    df = pd.read_sql(sql, engine, params=(linia, day))

    # --- normalizacja liczb i tekstów ---
    df["INDEKS"] = df["INDEKS"].astype("string").str.strip()
    df["JM"] = df["JM"].astype("string").str.strip()
    df["LINIA"] = df["LINIA"].astype("string").str.strip()
    df["ILOSC"] = (
        df["ILOSC"].astype("string").str.replace(",", ".", regex=False)
    )
    df["ILOSC"] = pd.to_numeric(df["ILOSC"], errors="coerce").fillna(0.0)

    # --- agregacja: na wszelki wypadek sumujemy metry, bo czasem index może się powtórzyć ---
    df_sum = cast(pd.DataFrame, df.groupby(["INDEKS", "JM", "LINIA"], as_index=False)["ILOSC"].sum())
    return df_sum

def add_workplace(workplace: str, speed_m_per_min: float, count_by_shift: float) -> bool:
    """Dodaje nową maszynę do bazy danych (INSERT)."""
    sql = f"INSERT INTO {PLAN_TABLE} (workplace, speed_m_per_min, count_by_shift) VALUES (?, ?, ?)"
    engine = _get_plan_engine()
    try:
        with engine.raw_connection() as conn:
            cur = conn.cursor()
            cur.execute(sql, (str(workplace).strip(), float(speed_m_per_min), float(count_by_shift)))
            conn.commit()
        return True
    except Exception as e:
        print(f"Błąd SQL (INSERT): {e}")
        return False

def update_workplace_full(workplace: str, speed_m_per_min: float, count_by_shift: float) -> bool:
    """Aktualizuje prędkość i sztuki dla istniejącej maszyny (UPDATE)."""
    sql = f"UPDATE {PLAN_TABLE} SET speed_m_per_min = ?, count_by_shift = ? WHERE workplace = ?"
    engine = _get_plan_engine()
    try:
        with engine.raw_connection() as conn:
            cur = conn.cursor()
            cur.execute(sql, (float(speed_m_per_min), float(count_by_shift), str(workplace).strip()))
            conn.commit()
        return True
    except Exception as e:
        print(f"Błąd SQL (UPDATE): {e}")
        return False

def delete_workplace(workplace: str) -> bool:
    """Usuwa maszynę z bazy danych (DELETE)."""
    sql = f"DELETE FROM {PLAN_TABLE} WHERE workplace = ?"
    engine = _get_plan_engine()
    try:
        with engine.raw_connection() as conn:
            cur = conn.cursor()
            cur.execute(sql, (str(workplace).strip(),))
            conn.commit()
        return True
    except Exception as e:
        print(f"Błąd SQL (DELETE): {e}")
        return False

def fetch_profiles_config() -> pd.DataFrame:
    """Pobiera konfigurację profili i czasów zbrojeń z bazy danych."""
    sql = f"SELECT profile, side, setting_time FROM {PROFILES_TABLE}"
    engine = _get_plan_engine()
    try:
        # Używamy pandas do szybkiego załadowania wyniku SQL do DataFrame
        df = pd.read_sql(sql, engine)
        return df
    except Exception as e:
        print(f"Błąd SQL (Odczyt profili): {e}")
        # Zwracamy pusty DataFrame w razie błędu (np. brak dostępu)
        return pd.DataFrame() 
    
def save_profile_to_db(profile: str, side: str, setting_time: int) -> bool:
    """Zapisuje nowy lub aktualizuje istniejący profil w bazie danych."""
    # Wymuszamy format zgodny z bazą (np. '0021')
    profile_clean = str(profile).strip()
    side_clean = str(side).strip().zfill(4)
    
    check_sql = f"SELECT COUNT(*) FROM {PROFILES_TABLE} WHERE profile = ? AND side = ?"
    update_sql = f"UPDATE {PROFILES_TABLE} SET setting_time = ? WHERE profile = ? AND side = ?"
    insert_sql = f"INSERT INTO {PROFILES_TABLE} (profile, side, setting_time) VALUES (?, ?, ?)"
    
    engine = _get_plan_engine()
    try:
        with engine.raw_connection() as conn:
            cur = conn.cursor()
            cur.execute(check_sql, (profile_clean, side_clean))
            row = cur.fetchone()
            exists = row[0] > 0 if row else False
            
            if exists:
                cur.execute(update_sql, (setting_time, profile_clean, side_clean))
            else:
                cur.execute(insert_sql, (profile_clean, side_clean, setting_time))
            conn.commit()
        return True
    except Exception as e:
        print(f"Błąd SQL (Zapis profilu): {e}")
        return False

def delete_profile_from_db(profile: str, side: str) -> bool:
    """Usuwa profil z bazy danych."""
    profile_clean = str(profile).strip()
    side_clean = str(side).strip().zfill(4)
    
    sql = f"DELETE FROM {PROFILES_TABLE} WHERE profile = ? AND side = ?"
    engine = _get_plan_engine()
    try:
        with engine.raw_connection() as conn:
            cur = conn.cursor()
            cur.execute(sql, (profile_clean, side_clean))
            deleted_rows = cur.rowcount  # Sprawdzamy, ile wierszy faktycznie usunięto
            conn.commit()
            
        if deleted_rows == 0:
            print(f"UWAGA SQL: Próbowano usunąć {profile_clean} ({side_clean}), ale nie znaleziono takiego wpisu w bazie.")
            return False
            
        return True
    except Exception as e:
        print(f"Błąd SQL (Usuwanie profilu): {e}")
        return False