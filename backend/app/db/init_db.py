from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

from app import models  # noqa: F401
from app.core.config import settings
from app.db.base import Base
from app.db.session import engine


def init_db() -> None:
    if engine.dialect.name == "postgresql":
        verify_migrations_current()
        return

    Base.metadata.create_all(bind=engine)


def alembic_config() -> Config:
    backend_root = Path(__file__).resolve().parents[2]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "alembic"))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    return config


def run_migrations() -> None:
    config = alembic_config()
    command.upgrade(config, "head")


def verify_migrations_current() -> None:
    config = alembic_config()
    expected_revision = ScriptDirectory.from_config(config).get_current_head()

    with engine.connect() as connection:
        if "alembic_version" not in inspect(connection).get_table_names():
            raise RuntimeError("Database migrations have not been applied. Run `alembic upgrade head`.")
        current_revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()

    if current_revision != expected_revision:
        raise RuntimeError(
            f"Database migration revision is {current_revision or 'unset'}, "
            f"expected {expected_revision}. Run `alembic upgrade head`."
        )
