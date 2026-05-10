from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.services.seed import seed_demo_data


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        row_count = seed_demo_data(db, force=True)
        print(f"Seeded {row_count} demo rows.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
