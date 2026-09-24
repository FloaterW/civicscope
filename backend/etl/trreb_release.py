"""Offline approved-release preparation and transactional Postgres publication.

No downloader, HTTP admin endpoint, scheduler, or implicit newest-vintage choice.
All commands use existing DATABASE_URL; credentials are never printed.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import tempfile

from sqlalchemy import insert, select, update
from sqlalchemy.exc import SQLAlchemyError

from app.models.trreb import TrrebRelease, TrrebObservation, TrrebPublication, TrrebPublicationEvent
from app.services.trreb_preview import MUNICIPALITIES
from app.services.trreb_validation import ATTRIBUTION, GEOGRAPHY_NOTE, VINTAGE_NOTE, validate_observation
from etl.audit_trreb import audit_history
from etl.trreb_archive import official_url

POLICY = 'as_published_static_reports_explicit_hashes_v1'
SCHEMA = 1


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def expected_reports():
    return ({('resale', f'{year}-{month:02}') for year in range(2020, 2026) for month in range(1, 13)}
            | {('resale_annual', str(year)) for year in range(2020, 2026)}
            | {('rental', f'{year}-Q{quarter}') for year in range(2020, 2026) for quarter in range(1, 5)})


def draft_manifest(root: Path):
    """Propose pins only when each period has exactly one validated vintage.

    If a period has revisions, an operator must write/review the explicit JSON
    selection; timestamp order is never a substitute for that decision.
    """
    path = root / 'trreb.sqlite'
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as db:
        rows = db.execute('SELECT family,period,sha256,status FROM reports ORDER BY family,period').fetchall()
    if len(rows) != 102 or {(r[0], r[1]) for r in rows} != expected_reports() or any(r[3] != 'validated' for r in rows):
        raise ValueError('Incomplete or ambiguous archive; explicitly select one validated SHA per required report')
    return {'schema_version': SCHEMA, 'revision_policy': POLICY,
            'archive_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'reports': [{'family': family, 'period': period, 'sha256': sha} for family, period, sha, _ in rows]}


def validate_manifest(manifest):
    if not isinstance(manifest, dict) or set(manifest) != {'schema_version', 'revision_policy', 'archive_sha256', 'reports'} or type(manifest.get('schema_version')) is not int or manifest.get('schema_version') != SCHEMA or manifest.get('revision_policy') != POLICY:
        raise ValueError('Unsupported release manifest or revision policy')
    if not re.fullmatch('[0-9a-f]{64}', str(manifest.get('archive_sha256', ''))):
        raise ValueError('Invalid archive hash')
    reports = manifest.get('reports')
    if not isinstance(reports, list) or len(reports) != 102:
        raise ValueError('Manifest must select all 102 source tables')
    pins = {}
    for row in reports:
        if not isinstance(row, dict) or set(row) != {'family', 'period', 'sha256'}:
            raise ValueError('Invalid report pin')
        if not all(isinstance(value, str) for value in row.values()):
            raise ValueError('Invalid report pin types')
        key = (row['family'], row['period'])
        if key not in expected_reports() or key in pins or not re.fullmatch('[0-9a-f]{64}', str(row['sha256'])):
            raise ValueError('Unexpected, duplicate or invalid report pin')
        pins[key] = row['sha256']
    if set(pins) != expected_reports():
        raise ValueError('Incomplete report pins')
    return pins


def _payload(db, report, geoid, area, parent):
    row = db.execute('SELECT * FROM resale WHERE report_id=? AND source_area=?', (report['id'], area)).fetchone()
    if row is None or row['property_type'] != 'all_home_types':
        raise ValueError('Missing or wrong-property municipal resale observation')
    for name in ('sales', 'median_price', 'property_days', 'listing_days'):
        if type(row[name]) is not int or row[name] < 0:
            raise ValueError('Invalid or absent resale headline statistic')
    if type(report['source_page']) is not int or report['source_page'] < 1:
        raise ValueError('Invalid source page')
    return {'geoid': geoid, 'source_area': area, 'period': report['period'],
            'period_type': 'year' if report['family'] == 'resale_annual' else 'month',
            'property_type': 'All home types', **{name: row[name] for name in ('median_price', 'sales', 'property_days', 'listing_days')},
            'source_url': official_url(report['source_url']), 'source_page': report['source_page'],
            'source_sha256': report['sha256'], 'warnings': [dict(r) for r in db.execute(
                'SELECT area,field,reported,children_sum,difference FROM quality_issues WHERE report_id=? AND area IN (?,?) ORDER BY area,field',
                (report['id'], area, parent))],
            'geography_note': GEOGRAPHY_NOTE, 'vintage_note': VINTAGE_NOTE, 'attribution': ATTRIBUTION}


def prepare_release(root: Path, manifest: dict):
    """Audit a selected snapshot, retaining other vintages in the original archive."""
    pins = validate_manifest(manifest)
    manifest = json.loads(canonical(manifest))
    path = root / 'trreb.sqlite'
    original_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    if original_hash != manifest['archive_sha256']:
        raise ValueError('Archive changed; review and approve a new manifest')
    with tempfile.TemporaryDirectory(prefix='civicscope-trreb-release-') as temporary:
        snapshot = Path(temporary) / 'trreb.sqlite'
        with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as source, closing(sqlite3.connect(snapshot)) as db:
            source.backup(db)
            db.row_factory = sqlite3.Row
            reports = [dict(row) for row in db.execute('SELECT * FROM reports')]
            selected = [row for row in reports if pins.get((row['family'], row['period'])) == row['sha256']]
            if len(selected) != 102 or any(row['status'] != 'validated' for row in selected):
                raise ValueError('Selected report not present or not validated')
            ids = {row['id'] for row in selected}
            for row in reports:
                if row['id'] not in ids:
                    for table in ('quality_issues', 'resale', 'rental_bedrooms', 'rental'):
                        db.execute(f'DELETE FROM {table} WHERE report_id=?', (row['id'],))
                    db.execute('DELETE FROM reports WHERE id=?', (row['id'],))
            db.commit()
            audit = audit_history(root, database_path=snapshot)
            if audit['errors']:
                raise ValueError('Selected corpus failed audit: ' + '; '.join(audit['errors']))
            observations = [_payload(db, report, geoid, area, parent)
                for report in sorted(selected, key=lambda r: (r['family'], r['period'])) if report['family'] != 'rental'
                for geoid, (area, parent) in sorted(MUNICIPALITIES.items())]
    if hashlib.sha256(path.read_bytes()).hexdigest() != original_hash:
        raise ValueError('Archive changed during release preparation')
    # Store provenance, not PDFs or all source tables. Rentals stay in their own
    # importer/archive and never become CMHC or public resale observations.
    summary = {key: audit[key] for key in ('coverage', 'monthly_resale_rows', 'annual_resale_rows',
        'rental_area_rows', 'rental_bedroom_rows')}
    summary['source_warning_counts'] = {key: len(audit[key]) for key in (
        'resale_source_total_discrepancies', 'rental_source_total_discrepancies', 'year_end_revision_differences')}
    result = {'schema_version': SCHEMA, 'manifest': manifest, 'audit_summary': summary, 'observations': observations}
    release = dict(result, release_id=digest(result))
    validate_release(release)
    return release


def validate_release(release):
    if not isinstance(release, dict) or set(release) != {'schema_version', 'manifest', 'audit_summary', 'observations', 'release_id'}:
        raise ValueError('Invalid release shape')
    pins = validate_manifest(release['manifest'])
    content = {key: release[key] for key in ('schema_version', 'manifest', 'audit_summary', 'observations')}
    if type(release['schema_version']) is not int or release['schema_version'] != SCHEMA or release['release_id'] != digest(content):
        raise ValueError('Release content hash mismatch')
    summary = release['audit_summary']
    if not isinstance(summary, dict) or set(summary) != {'coverage', 'monthly_resale_rows', 'annual_resale_rows', 'rental_area_rows', 'rental_bedroom_rows', 'source_warning_counts'}:
        raise ValueError('Invalid release audit summary')
    coverage = summary['coverage']
    counts = {'resale': 72, 'resale_annual': 6, 'rental': 24}
    if coverage != {family: {'expected': count, 'imported': count, 'missing': [], 'unexpected': []} for family, count in counts.items()}:
        raise ValueError('Incomplete audited report coverage')
    for key, count in {'monthly_resale_rows': 2952, 'annual_resale_rows': 246, 'rental_area_rows': 965, 'rental_bedroom_rows': 3860}.items():
        if type(summary[key]) is not int or summary[key] != count:
            raise ValueError('Incomplete audited row coverage')
    warnings = summary['source_warning_counts']
    if not isinstance(warnings, dict) or set(warnings) != {'resale_source_total_discrepancies', 'rental_source_total_discrepancies', 'year_end_revision_differences'} or any(type(v) is not int or v < 0 for v in warnings.values()):
        raise ValueError('Invalid audited warning counts')
    if not isinstance(release['observations'], list):
        raise ValueError('Invalid observations')
    for row in release['observations']:
        validate_observation(row, pins)
    expected = {(geoid, period) for geoid in MUNICIPALITIES for family, period in expected_reports() if family != 'rental'}
    keys = [(row['geoid'], row['period']) for row in release['observations']]
    if len(keys) != 1950 or set(keys) != expected:
        raise ValueError('Release must contain exactly 1,950 municipal resale observations')


def import_release(engine, release):
    """Insert all or nothing; never activate on import or overwrite a release."""
    validate_release(release)
    release_id = release['release_id']
    with engine.begin() as connection:
        # Local SQLite creates metadata without Alembic (PostGIS migrations are
        # production-only). Production must retain the migrated singleton.
        if connection.dialect.name == 'sqlite' and connection.execute(select(TrrebPublication.id)).first() is None:
            connection.execute(insert(TrrebPublication), [{'id': 1, 'release_id': None}])
        existing = connection.execute(select(TrrebRelease.id).where(TrrebRelease.id == release_id)).scalar_one_or_none()
        if existing:
            stored = _stored_release(connection, release_id)
            validate_release(stored)
            if canonical(stored) != canonical(release):
                raise ValueError('Immutable release differs from existing storage')
            return release_id
        connection.execute(insert(TrrebRelease), [{'id': release_id, 'archive_sha256': release['manifest']['archive_sha256'],
            'manifest': release['manifest'], 'audit_summary': release['audit_summary'], 'created_at': datetime.now(timezone.utc)}])
        connection.execute(insert(TrrebObservation), [{'release_id': release_id, 'geoid': row['geoid'],
            'period': row['period'], 'payload': row} for row in release['observations']])
    return release_id


def _stored_release(connection, release_id):
    row = connection.execute(select(TrrebRelease.__table__).where(TrrebRelease.id == release_id)).mappings().one_or_none()
    if row is None:
        raise ValueError('Unknown release')
    observations = list(connection.execute(select(TrrebObservation.payload).where(TrrebObservation.release_id == release_id)).scalars())
    # Match the canonical preparation ordering, independent of DB query ordering.
    observations.sort(key=lambda r: ('resale_annual' if r['period_type'] == 'year' else 'resale', r['period'], r['geoid']))
    return {'schema_version': SCHEMA, 'release_id': release_id, 'manifest': row['manifest'],
            'audit_summary': row['audit_summary'], 'observations': observations}


def activate_release(engine, release_id, *, expected_active, reason):
    """Compare-and-swap publication with an audit trail; None disables immediately."""
    if not reason.strip() or len(reason) > 500:
        raise ValueError('A concise activation/rollback reason is required')
    with engine.begin() as connection:
        if release_id is not None:
            validate_release(_stored_release(connection, release_id))
        current = connection.execute(select(TrrebPublication.release_id).where(TrrebPublication.id == 1).with_for_update()).first()
        if current is None:
            raise ValueError('Publication singleton missing; apply migration first')
        if current[0] != expected_active:
            raise ValueError('Active release changed; review before switching')
        predicate = TrrebPublication.release_id.is_(None) if expected_active is None else TrrebPublication.release_id == expected_active
        result = connection.execute(update(TrrebPublication).where(TrrebPublication.id == 1, predicate).values(release_id=release_id))
        if result.rowcount != 1:
            raise ValueError('Concurrent publication change')
        connection.execute(insert(TrrebPublicationEvent), [{'release_id': release_id, 'reason': reason,
            'created_at': datetime.now(timezone.utc)}])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    draft = commands.add_parser('draft-manifest')
    draft.add_argument('--root', type=Path, required=True)
    draft.add_argument('--output', type=Path, required=True)
    load = commands.add_parser('import')
    load.add_argument('--root', type=Path, required=True)
    load.add_argument('--manifest', type=Path, required=True)
    prepare = commands.add_parser('prepare')
    prepare.add_argument('--root', type=Path, required=True)
    prepare.add_argument('--manifest', type=Path, required=True)
    prepare.add_argument('--output', type=Path, required=True)
    bundle = commands.add_parser('import-bundle')
    bundle.add_argument('--bundle', type=Path, required=True)
    bundle.add_argument('--approved-release', required=True, help='Previously reviewed exact release content SHA')
    switch = commands.add_parser('activate')
    switch.add_argument('--release', required=True, help='Exact release SHA, or none to disable')
    switch.add_argument('--expected-active', required=True, help='Current release SHA, or none')
    switch.add_argument('--reason', required=True)
    commands.add_parser('status')
    args = parser.parse_args()
    if args.command == 'draft-manifest':
        # Exclusive create prevents accidentally replacing reviewed selection.
        with args.output.open('x', encoding='utf-8') as output:
            json.dump(draft_manifest(args.root), output, indent=2)
        print('Draft written; review the exact report SHA selections before importing.')
        return
    if args.command == 'prepare':
        release = prepare_release(args.root, json.loads(args.manifest.read_text(encoding='utf-8')))
        with args.output.open('x', encoding='utf-8') as output:
            output.write(canonical(release))
        print(json.dumps({'prepared_release': release['release_id'], 'observations': 1950, 'activated': False}))
        return
    from app.db.session import engine
    if args.command == 'import':
        release = prepare_release(args.root, json.loads(args.manifest.read_text(encoding='utf-8')))
        print(json.dumps({'imported_release': import_release(engine, release), 'observations': 1950, 'activated': False}))
    elif args.command == 'import-bundle':
        release = json.loads(args.bundle.read_text(encoding='utf-8'))
        if not isinstance(release, dict) or release.get('release_id') != args.approved_release:
            raise ValueError('Bundle does not match the separately approved release SHA')
        print(json.dumps({'imported_release': import_release(engine, release), 'observations': 1950, 'activated': False}))
    elif args.command == 'activate':
        activate_release(engine, None if args.release == 'none' else args.release,
            expected_active=None if args.expected_active == 'none' else args.expected_active, reason=args.reason)
        print(json.dumps({'active_release': args.release}))
    else:
        with engine.connect() as connection:
            active = connection.execute(select(TrrebPublication.release_id).where(TrrebPublication.id == 1)).scalar_one_or_none()
            releases = connection.execute(select(TrrebRelease.id, TrrebRelease.created_at).order_by(TrrebRelease.created_at)).all()
        print(json.dumps({'active_release': active, 'releases': [{'id': row[0], 'created_at': str(row[1])} for row in releases]}))


if __name__ == '__main__':
    try:
        main()
    except SQLAlchemyError:
        raise SystemExit('Database operation failed; no activation was completed. Check authorized connectivity and migrations without sharing credentials.') from None
    except (ValueError, OSError, sqlite3.Error) as exc:
        raise SystemExit(f'TRREB release rejected: {exc}') from None
