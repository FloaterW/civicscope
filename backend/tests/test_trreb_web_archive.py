"""Validate the public snapshot using the original backend schema/crosswalk."""
import json
from pathlib import Path

from app.services.trreb_preview import MUNICIPALITIES
from app.services.trreb_validation import validate_observation
from etl.trreb_release import expected_reports


def test_public_web_archive_schema_and_complete_coverage():
    path = Path(__file__).resolve().parents[2] / 'frontend/data/trreb-resale-2020-2025.json'
    archive = json.loads(path.read_text(encoding='utf-8'))
    assert set(archive) == {'schema_version', 'source_release', 'observations'}
    assert archive['schema_version'] == 1
    assert archive['source_release'] == '253fbe7ac0c9668b08d60cc9034aaa9cf81cbc992273fe736e056c5f6148329d'
    rows = archive['observations']
    assert len(rows) == 1950
    assert {(r['geoid'], r['period']) for r in rows} == {
        (geoid, period) for geoid in MUNICIPALITIES
        for family, period in expected_reports() if family != 'rental'
    }
    for row in rows:
        validate_observation(row)
