"""Interpret Statistics Canada's Census Profile CL_FLAG before numeric parsing."""


def observation_value(row):
    # 1 unavailable, 2 not applicable, 3 caution, 4 unreliable,
    # 5 revised, 6 confidential, 7 revised/caution, O missing.
    # Withhold caution values until the application can carry their flag.
    # Genuine unflagged zeros and revised published figures remain numbers.
    flag = str(row.get("FLAG") or "").strip()
    return row.get("OBS_VALUE") if flag in ("", "5", "r") else None
