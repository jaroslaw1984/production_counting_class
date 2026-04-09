import math
import holidays
from datetime import date, timedelta

SHIFTS_PER_DAY = 3

# Inicjujemy polski kalendarz świąt (wczytuje się raz przy starcie programu)
PL_HOLIDAYS = holidays.CountryHoliday('PL')

def pl_weekday_name(d: date) -> str:
    # --- Zwraca polską nazwę dnia tygodnia. --- 
    names = ["poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela"]
    return names[d.weekday()]

def shifts_per_day_for_date(d: date, work_saturday: bool, work_sunday: bool) -> int:
    # 1. Pełen automat: polskie święto (0 zmian)
    if d in PL_HOLIDAYS:
        return 0
        
    # 2. Sobota (d.weekday() == 5)
    if d.weekday() == 5:
        return 1 if work_saturday else 0
        
    # 3. Niedziela (d.weekday() == 6)
    if d.weekday() == 6:
        return 1 if work_sunday else 0
        
    # 4. Zwykły dzień roboczy: 3 zmiany
    return SHIFTS_PER_DAY

def next_valid_date(d: date, work_saturday: bool, work_sunday: bool) -> date:
    d += timedelta(days=1)
    while shifts_per_day_for_date(d, work_saturday, work_sunday) == 0:
        d += timedelta(days=1)
    return d

def add_shifts(start_date: date, start_shift: int, shifts_count: int, work_saturday: bool, work_sunday: bool) -> tuple[date, int]:
    if shifts_count <= 0:
        return start_date, start_shift

    d = start_date
    if shifts_per_day_for_date(d, work_saturday, work_sunday) == 0:
        d = next_valid_date(d, work_saturday, work_sunday)
        start_shift = 1

    max_shifts_today = shifts_per_day_for_date(d, work_saturday, work_sunday)
    s = int(start_shift)
    if s < 1: s = 1
    if s > max_shifts_today: s = 1

    moves = int(shifts_count) - 1
    for _ in range(max(0, moves)):
        max_shifts_today = shifts_per_day_for_date(d, work_saturday, work_sunday)
        s += 1
        if s > max_shifts_today:
            d = next_valid_date(d, work_saturday, work_sunday)
            s = 1

    return d, s

def round_shifts_custom(shifts: float) -> int:
    # --- Funkcja do zaokrąglania zmian (4.5 w dół, 4.7 w górę). ---
    frac = shifts - math.floor(shifts)
    return math.floor(shifts) if frac < 0.6 else math.ceil(shifts)