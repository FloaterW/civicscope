from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.routes import router as api_router
from app.core.config import settings
from app.db.init_db import init_db
from app.db.session import SessionLocal, get_db
from app.services.seed import seed_cmhc_data, seed_demo_data


def create_app(auto_initialize: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if auto_initialize:
            init_db()
            if settings.seed_on_startup:
                db = SessionLocal()
                try:
                    seed_demo_data(db, force=settings.force_reseed)
                    seed_cmhc_data(db, force=settings.force_reseed)
                finally:
                    db.close()
        yield

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Geospatial civic analytics API for Greater Toronto housing affordability metrics.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    @app.get("/health", tags=["system"])
    def health(db: Session = Depends(get_db)):
        try:
            db.execute(text("SELECT 1"))
            db_status = "ok"
        except Exception:
            db_status = "unavailable"
        status = "ok" if db_status == "ok" else "degraded"
        return {"status": status, "service": "civicscope-api", "database": db_status}

    app.include_router(api_router)
    return app


app = create_app()
