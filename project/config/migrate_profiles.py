import pandas as pd
import urllib.parse
from sqlalchemy import create_engine, text
import pyodbc

# Parametry serwera
PLAN_SERVER = "kronos.sip.local"
PLAN_DB = "Raporty"
CSV_PATH = "profile_config.csv"
TABLE_NAME = "tblPlanowanieProfilesSetAndTime"

def _pick_driver() -> str:
    """Wykrywa dostępny sterownik ODBC zainstalowany w systemie."""
    drivers = pyodbc.drivers()
    for name in ("ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server", "SQL Server"):
        if name in drivers:
            return name
    raise RuntimeError(f"Brak sterownika SQL Server. Dostępne: {drivers}")

def migrate_data():
    print("Rozpoczynam ponowną migrację z poprawką formatowania...")
    
    # 1. Wczytanie danych z CSV z wymuszeniem typów tekstowych
    try:
        print(f"Wczytywanie pliku {CSV_PATH}...")
        # Jawne wskazanie dtype zapobiega automatycznej konwersji tekstów z zerami na liczby
        df = pd.read_csv(CSV_PATH, sep=";", dtype={"profile": str, "side": str})
        
        # Dodatkowe oczyszczenie spacji i upewnienie się, że format zachowuje dopełnienie zerami (np. 4 znaki)
        df["profile"] = df["profile"].astype(str).str.strip()
        df["side"] = df["side"].astype(str).str.strip().str.zfill(4)
        df["setting_time"] = pd.to_numeric(df["setting_time"], errors="coerce").fillna(0).astype(int)
        
        print(f"Wczytano {len(df)} wierszy. Przykładowa strona po korekcie: {df['side'].iloc[0]}")
    except Exception as e:
        print(f"Błąd podczas wczytywania CSV: {e}")
        return
    
    # 2. Utworzenie połączenia
    try:
        driver = _pick_driver()
    except Exception as e:
        print(e)
        return

    conn_str = (
        f"DRIVER={{{driver}}};"
        f"SERVER={PLAN_SERVER};"
        f"DATABASE={PLAN_DB};"
        "Trusted_Connection=yes;"
        "Encrypt=yes;"
        "TrustServerCertificate=yes;"
    )
    quoted_conn_str = urllib.parse.quote_plus(conn_str)
    engine = create_engine(f"mssql+pyodbc:///?odbc_connect={quoted_conn_str}")
    
    # 3. Czyszczenie tabeli i ponowny zrzut danych do bazy
    try:
        # Używamy engine.begin(), aby wykonać operacje w jednej transakcji
        with engine.begin() as conn:
            print(f"Czyszczenie tabeli {TABLE_NAME} z błędnych rekordów...")
            conn.execute(text(f"DELETE FROM {TABLE_NAME}"))
            
            print(f"Zapisywanie poprawnie sformatowanych danych...")
            df.to_sql(TABLE_NAME, con=conn, schema="dbo", if_exists="append", index=False)
            
        print("Migracja zakończona sukcesem! Dane w bazie zachowały początkowe zera (np. 0021).")
    except Exception as e:
        print(f"Wystąpił błąd podczas operacji na bazie SQL: {e}")

if __name__ == "__main__":
    migrate_data()