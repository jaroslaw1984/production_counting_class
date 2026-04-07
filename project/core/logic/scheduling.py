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

def shifts_per_day_for_date(d: date, include_weekends: bool) -> int:
    # --- Zwraca liczbę dostępnych zmian dla danej daty. ---
    
    # 1. Pełen automat: Jeśli to polskie święto, maszyna nie pracuje (0 zmian)
    if d in PL_HOLIDAYS:
        return 0
        
    # 2. Weekendy: 1 zmiana (jeśli uwzględnione) lub 0 zmian
    if d.weekday() >= 5:  # 5=sobota, 6=niedziela
        return 1 if include_weekends else 0
        
    # 3. Zwykły dzień roboczy: 3 zmiany
    return SHIFTS_PER_DAY

def next_valid_date(d: date, include_weekends: bool) -> date:
    # --- Zastępuje stare next_workday. Przeskakuje do najbliższego dnia, 
    # --- który ma więcej niż 0 zmian do przepracowania (pomija święta i ew. weekendy).
    d += timedelta(days=1)
    while shifts_per_day_for_date(d, include_weekends) == 0:
        d += timedelta(days=1)
    return d

def add_shifts(start_date: date, start_shift: int, shifts_count: int, include_weekends: bool) -> tuple[date, int]:
    # --- Główny algorytm wyliczający datę i zmianę zakończenia. ---
    if shifts_count <= 0:
        return start_date, start_shift

    d = start_date
    
    # --- Jeśli startujemy w dniu, który odgórnie ma 0 zmian (np. dzisiaj jest 1 Maja) 
    # --- to od razu przeskakujemy na najbliższy prawidłowy dzień pracujący.
    if shifts_per_day_for_date(d, include_weekends) == 0:
        d = next_valid_date(d, include_weekends)
        start_shift = 1

    # --- Ustalenie poprawnej zmiany startowej ---
    max_shifts_today = shifts_per_day_for_date(d, include_weekends)
    s = int(start_shift)
    if s < 1: 
        s = 1
    if s > max_shifts_today:
        s = 1 # Reset do 1, jeśli np. maszyna w weekend ma max 1 zmianę, a podano 3

    # --- Pętla "skacząca" o shifts_count - 1 razy ---
    moves = int(shifts_count) - 1
    for _ in range(max(0, moves)):
        max_shifts_today = shifts_per_day_for_date(d, include_weekends)
        
        s += 1
        if s > max_shifts_today:
            # Skończyły się zmiany w tym dniu -> Przejście na następny pracujący dzień
            d = next_valid_date(d, include_weekends)
            s = 1

    return d, s

def round_shifts_custom(shifts: float) -> int:
    # --- Funkcja do zaokrąglania zmian (4.5 w dół, 4.7 w górę). ---
    frac = shifts - math.floor(shifts)
    return math.floor(shifts) if frac < 0.6 else math.ceil(shifts)