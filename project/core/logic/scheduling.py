import math
from datetime import date, timedelta

SHIFTS_PER_DAY = 3

def pl_weekday_name(d: date) -> str:
    # --- Zwraca polską nazwę dnia tygodnia. --- 
    names = ["poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela"]
    return names[d.weekday()]

def next_workday(d: date) -> date:
    # --- Przeskakuje do najbliższego dnia roboczego (poniedziałku). ---
    d += timedelta(days=1)
    while d.weekday() >= 5:  # 5=sobota, 6=niedziela
        d += timedelta(days=1)
    return d

def shifts_per_day_for_date(d: date, include_weekends: bool) -> int:
    # --- Zwraca liczbę dostępnych zmian dla danej daty. ---
    # --- Pn-Pt: 3 zmiany. ---
    # --- Sob-Nd: 1 zmiana (tylko jeśli maszyna pracuje w weekend), w przeciwnym razie 0. ---
    if d.weekday() >= 5:  # Weekend
        return 1 if include_weekends else 0
    return SHIFTS_PER_DAY

def add_shifts(start_date: date, start_shift: int, shifts_count: int, include_weekends: bool) -> tuple[date, int]:
    # --- Główny algorytm wyliczający datę i zmianę zakończenia. ---
    # --- Przesuwa się o określoną liczbę zmian (shifts_count). ---
    if shifts_count <= 0:
        return start_date, start_shift

    d = start_date
    
    # --- Jeśli maszyna NIE pracuje w weekend, a startujemy w sobotę/niedzielę -> przesuń na poniedziałek ---
    if not include_weekends and d.weekday() >= 5:
        d = next_workday(d)

    # --- Ustalenie poprawnej zmiany startowej
    max_shifts_today = shifts_per_day_for_date(d, include_weekends)
    s = int(start_shift)
    if s < 1: s = 1
    if s > max_shifts_today and max_shifts_today > 0:
        s = 1 # Jeśli startujemy w weekend (1 zmiana), a user wybrał zmianę 2/3 -> reset do 1

    # --- Pętla "skacząca" o shifts_count - 1 razy (bo startujemy już na pierwszej zmianie) ---
    moves = int(shifts_count) - 1
    for _ in range(max(0, moves)):
        max_shifts_today = shifts_per_day_for_date(d, include_weekends)
        
        s += 1
        if s > max_shifts_today or max_shifts_today == 0:
            # Przejście na następny dzień
            s = 1
            if include_weekends:
                d += timedelta(days=1)
            else:
                d = next_workday(d)
                
            # --- Ponowne sprawdzenie limitu zmian dla nowego dnia ---
            max_shifts_today = shifts_per_day_for_date(d, include_weekends)
            if max_shifts_today == 0: # Zabezpieczenie
                d = next_workday(d)
                s = 1

    return d, s

def round_shifts_custom(shifts: float) -> int:
    # --- Funkcja do zaokrąglania zmian według niestandardowych reguł (4.5 w dół, 4.7 w górę). ---
    frac = shifts - math.floor(shifts)
    return math.floor(shifts) if frac < 0.6 else math.ceil(shifts)