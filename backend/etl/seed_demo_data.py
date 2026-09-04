from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.services.seed import (
    seed_cmhc_data,
    seed_cmhc_tract_data,
    seed_demo_data,
    seed_transit_scores,
)


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        counts = {
            "census": seed_demo_data(db, force=True),
            "cmhc_municipal": seed_cmhc_data(db, force=True),
            "cmhc_tract": seed_cmhc_tract_data(db, force=True),
            "transit_tract": seed_transit_scores(db, force=True),
        }
        summary = ", ".join(f"{name}={count}" for name, count in counts.items())
        print(f"Seeded packaged application data: {summary}.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
