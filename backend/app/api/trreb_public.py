"""Flagged read-only resale API backed only by an explicitly activated release."""
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.trreb_public import public_enabled, read_public_resale

router = APIRouter()


@router.get('/api/trreb/resale/{geoid}', tags=['TRREB resale'], include_in_schema=False)
def resale(geoid: str, response: Response, year: int = Query(2025, ge=2020, le=2025),
           month: int | None = Query(None, ge=1, le=12), db: Session = Depends(get_db)):
    if not public_enabled():
        raise HTTPException(404, 'Not found')
    try:
        payload = read_public_resale(db, geoid, year, month)
    except LookupError:
        raise HTTPException(404, 'No municipal TRREB reporting area') from None
    except (ValueError, SQLAlchemyError):
        raise HTTPException(503, 'TRREB resale data is temporarily unavailable') from None
    # Pointer changes and emergency disable must take effect without CDN expiry.
    response.headers['Cache-Control'] = 'no-store'
    return payload
