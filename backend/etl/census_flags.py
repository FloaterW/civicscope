"""Statistics Canada CL_FLAG: never turn a suppressed filler into a zero."""


def observation_value(row):
    # CL_FLAG: 1 unavailable; 2 not applicable; 3 caution; 4 unreliable;
    # 5 revised; 6 confidential; 7 revised/caution; O missing.
    # Caution values are withheld until the application can carry their flag.
    # Unflagged genuine zeros and revised published figures remain numbers.
    flag = str(row.get("FLAG") or "").strip()
    return row.get("OBS_VALUE") if flag in ("", "5", "r") else None
