from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from sqlalchemy import text
from sqlalchemy.orm import Session

import logging

from app.api.routes import router as api_router
from app.core.config import settings, validate_environment
from app.db.init_db import init_db
from app.db.session import SessionLocal, get_db
from app.services.seed import seed_cmhc_data, seed_cmhc_tract_data, seed_demo_data, seed_transit_scores

limiter = Limiter(key_func=get_remote_address, default_limits=[settings.rate_limit])


def create_app(auto_initialize: bool = True) -> FastAPI:
    logger = logging.getLogger("civicscope")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        for warning in validate_environment():
            logger.warning(warning)
        if auto_initialize:
            init_db()
            if settings.seed_on_startup:
                db = SessionLocal()
                try:
                    seed_demo_data(db, force=settings.force_reseed)
                    seed_cmhc_data(db, force=settings.force_reseed)
                    seed_cmhc_tract_data(db, force=settings.force_reseed)
                    seed_transit_scores(db, force=settings.force_reseed)
                except Exception:
                    db.rollback()
                    raise
                finally:
                    db.close()
        yield

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Geospatial civic analytics API for Greater Toronto housing affordability metrics.",
        lifespan=lifespan,
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "HEAD", "OPTIONS"],
        allow_headers=["Accept", "Accept-Language", "Content-Type"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    CACHEABLE_PREFIXES = (
        "/api/map-data",
        "/api/summary",
        "/api/compare",
        "/api/metrics",
        "/api/transit-routes",
    )

    @app.middleware("http")
    async def security_and_cache_headers(request: Request, call_next):
        response: Response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")
        if (
            request.method == "GET"
            and response.status_code < 400
            and request.url.path.startswith(CACHEABLE_PREFIXES)
        ):
            response.headers.setdefault("Cache-Control", "public, max-age=3600, stale-while-revalidate=86400")
        return response

    @app.get("/health", tags=["system"], operation_id="health_check")
    @app.head("/health", tags=["system"], include_in_schema=False)
    def health(db: Session = Depends(get_db)):
        try:
            db.execute(text("SELECT 1"))
            db_status = "ok"
        except Exception:
            db_status = "unavailable"
        status = "ok" if db_status == "ok" else "degraded"
        payload = {"status": status, "service": "civicscope-api", "database": db_status}
        if db_status != "ok":
            return JSONResponse(status_code=503, content=payload)
        return payload

    app.include_router(api_router)
    return app


app = create_app()
