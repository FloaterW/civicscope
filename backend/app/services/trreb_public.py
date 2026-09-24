"""Read approved municipal reporting context; no polygon joins or public writes."""
import os

from sqlalchemy.orm import Session

from app.models.trreb import TrrebObservation, TrrebPublication
from app.services.trreb_preview import MUNICIPALITIES
from app.services.trreb_validation import validate_observation


def public_enabled():
    return os.getenv('TRREB_PUBLIC_ENABLED') == '1'


def read_public_resale(db: Session, geoid: str, year: int, month: int | None):
    if geoid not in MUNICIPALITIES:
        raise LookupError('No municipal TRREB reporting area')
    publication = db.get(TrrebPublication, 1)
    if publication is None or publication.release_id is None:
        raise ValueError('No active release')
    period = str(year) if month is None else f'{year}-{month:02}'
    observation = db.get(TrrebObservation, (publication.release_id, geoid, period))
    if observation is None:
        raise ValueError('Missing approved observation')
    validate_observation(observation.payload)
    if observation.payload['geoid'] != geoid or observation.payload['period'] != period:
        raise ValueError('Observation does not match requested geography/period')
    return dict(observation.payload, release_id=publication.release_id, preview_only=False)
