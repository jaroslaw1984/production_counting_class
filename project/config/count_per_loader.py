import pandas as pd
import pyodbc
from sqlalchemy import create_engine
import urllib.parse
from typing import cast

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


