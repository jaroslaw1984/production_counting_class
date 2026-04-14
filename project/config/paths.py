from pathlib import Path

# --- podstawowa ścieżka projektu (katalog "project") ---
BASE_DIR = Path(__file__).resolve().parent.parent

# --- stała ścieżka do pliku konfiguracyjnego --- 
CONFING_PATH = BASE_DIR / "config" / "profile_config.csv"
MACHINE_CONFIG_PATH = BASE_DIR / "config" / "machine_config.csv"
SHIFTS_PER_DAY = 3

# --- ścieżka do pliku z helpem ---
HELP_SECTIONS_PATH = BASE_DIR / "data" / "help_sections.json"
HELP_SECTIONS_IMAGES = BASE_DIR / "data" / "help_images"
LATEST_JSON_PATH = r"\\na02\groups\Produkcja\Planowanie OKL\Production Counter Program\latest.json"


# --- ścieżki do serwera
SERVER = r"sipdbprod\hydms1"
DATABASE = "hydrawlo"
VIEW_FULLNAME = "hydadm.SOP_Abfrage_Auftragsbestand_Sochacki"
SAP_SERVER = "kronos.sip.local"
SAP_DATABASE = "Raporty"

# --- ścieżka do szablonu raportu DOCX ---
REPORT_TEMPLATE_PATH = BASE_DIR / "core"/ "logic" / "templates" / "report_template.docx"