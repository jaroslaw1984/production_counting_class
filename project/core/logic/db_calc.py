from platform import machine

import pandas as pd
from datetime import date
from project.core.logic.scheduling import add_shifts, pl_weekday_name, round_shifts_custom

def build_db_report_pieces(
    df: pd.DataFrame,
    df_cfg: pd.DataFrame,
    selected_machines: list[str],
    pps_by_machine: dict[str, int],
    start_d: date,
    start_shift: int,
    saturday_by_machine: dict[str, bool],
    sunday_by_machine: dict[str, bool]
) -> str:
    lines = []
    lines.append("---- Przewidywane zakończenie produkcji --- \n")

    # --- iteracja po maszynach ---
    for machine in selected_machines:
        df_one = df[df["workplace"] == machine].copy()
        m_sat = saturday_by_machine.get(machine, False)
        m_sun = sunday_by_machine.get(machine, False)
        if df_one.empty:
            lines.append(f"=== {machine} ===")
            lines.append("Brak danych.\n")
            continue

        # --- obliczenia produkcji ---
        target_value = pd.to_numeric(df_one["target_value_pcs"], errors="coerce").fillna(0)
        good_qty = pd.to_numeric(df_one["good_qty_pcs"], errors="coerce").fillna(0)

        remaining = (target_value - good_qty).clip(lower=0)
        total_remaining = float(remaining.sum())

        pps = int(pps_by_machine.get(machine, 0))

        lines.append(f"=== {machine} ===")
        lines.append(f"Pozostało: {total_remaining:.0f} szt.")

        if pps <= 0:
            lines.append("Szt./zmianę: BRAK / 0 (nie da się policzyć zmian)\n")
            continue

        # --- zbrojenia (tak samo jak Excel) ---
        # normalizacja kluczy
        df_one["profile"] = df_one["profile"].astype("string").str.strip()
        df_one["side"] = df_one["side"].astype("string").str.strip().str.zfill(4)

        cfg = df_cfg.copy()
        cfg["profile"] = cfg["profile"].astype("string").str.strip()
        cfg["side"] = cfg["side"].astype("string").str.strip().str.zfill(4)

        # --- scalenie - merge setting_time ---
        df_one = df_one.merge(
            cfg[["profile", "side", "setting_time"]],
            on=["profile", "side"],
            how="left",
        )
        
        missing = df_one[df_one["setting_time"].isna()]
        if not missing.empty:
            sample = missing[["profile", "side"]].drop_duplicates().head(15)
            lines.append("⚠️ Brak czasu zbrojenia w pliku profile_config.csv dla kluczy 'profile, side':")
            lines.append(sample.to_string(index=False))
            # i dopiero wtedy fillna(0) żeby program nie padł            

        df_one["setting_time"] = pd.to_numeric(df_one["setting_time"], errors="coerce").fillna(0).astype(int)
        
        # --- ZBROJENIA: liczymy ZMIANY w kolejności (bloki), nie unikalne wartości ---
        # --- ważne: DB czasem nie jest posortowane – sortuj po zleceniu (jeśli masz) ---
        if "order_id" in df_one.columns:
            # order_id bywa stringiem z zerami – normalizujemy do liczby pomocniczej ---
            df_one["_order_num"] = (
                df_one["order_id"].astype("string").str.replace(r"\.0$", "", regex=True).str.lstrip("0")
            )
            df_one["_order_num"] = pd.to_numeric(df_one["_order_num"], errors="coerce")
            df_one = df_one.sort_values(["_order_num"], kind="stable").drop(columns=["_order_num"])

        # --- klucz zbrojenia – zwykle profil+strona; jeśli strona zawsze 0020, i tak zadziała ---
        keys = list(zip(df_one["profile"].astype("string").str.strip(),
                        df_one["side"].astype("string").str.strip().str.zfill(4)))

        setup_count = 0
        setup_min = 0.0

        prev_key = None
        for key, st in zip(keys, df_one["setting_time"].tolist()):
            if prev_key is None:
                # --- start – zakładamy, że pierwsze ustawienie już jest na maszynie (nie liczymy jako zbrojenie) ---
                prev_key = key
                continue

            if key != prev_key:
                st_val = float(st or 0)
                if st_val > 0:
                    setup_count += 1
                    setup_min += st_val
                prev_key = key

        setup_shifts = setup_min / (8 * 60)            

        # --- zmiany: produkcja + zbrojenia ---
        prod_shifts = total_remaining / pps if total_remaining > 0 else 0.0
        shifts_exact = prod_shifts + setup_shifts
        shifts_rounded = round_shifts_custom(shifts_exact)
        
        # Zamiast dodawać do zaokrąglonych zmian, dodaj do surowego wyniku (float)
        buffer_shifts = 0.5 
        shifts_exact = prod_shifts + setup_shifts + buffer_shifts
        shifts_count = round_shifts_custom(shifts_exact) 

        # --- koniec produkcji dla tej maszyny ---
        end_d, end_s = add_shifts(
            start_date=start_d,
            start_shift=start_shift,
            shifts_count=shifts_count,
            work_saturday=m_sat,   
            work_sunday=m_sun    
        )

        # --- raport dla tej maszyny ---
        lines.append(f"Szt./zmianę: {pps}")
        lines.append(f"Ilość zbrojeń profili: {setup_count}")
        lines.append(f"Czas zbrojeń: {setup_min:.0f} min")
        lines.append(f"Zmiany (8h): {shifts_exact:.2f} → {shifts_rounded}")
        lines.append(f"Start liczenia: {pl_weekday_name(start_d)} ({start_d.isoformat()}) zmiana {start_shift}")
        lines.append("---------------------------------------------------------------------")
        lines.append(f"Przewidywana produkcja do: {pl_weekday_name(end_d)} (zmiana {end_s}) ({end_d.strftime('%d.%m.%Y')})\n")

    return "\n".join(lines)