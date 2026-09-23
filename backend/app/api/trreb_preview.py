"""Loopback-only preview endpoint; absent data and closed permissions fail closed."""
import os
from pathlib import Path
import sqlite3

from fastapi import APIRouter, HTTPException, Query, Request, Response

from app.core.config import settings
from app.services.trreb_preview import MUNICIPALITIES, read_resale

router=APIRouter()


@router.get('/api/trreb-preview/{geoid}',include_in_schema=False)
def resale_preview(geoid: str, request: Request, response: Response,
                   year: int=Query(2025,ge=2020,le=2025),
                   month: int | None=Query(None,ge=1,le=12)):
    if settings.app_env!='development' or os.getenv('TRREB_PREVIEW_ENABLED')!='1' or not request.client or request.client.host not in {'127.0.0.1','::1','testclient'}:
        raise HTTPException(404,'Not found')
    if geoid not in MUNICIPALITIES:
        raise HTTPException(404,'No municipal TRREB reporting area')
    path=os.getenv('TRREB_DATABASE')
    if not path:
        raise HTTPException(503,'Local historical database is not configured')
    try:
        payload=read_resale(Path(path),geoid,year,month)
    except (OSError,ValueError,sqlite3.Error):
        raise HTTPException(503,'TRREB preview is unavailable or requires validation') from None
    response.headers['Cache-Control']='no-store'
    return payload
