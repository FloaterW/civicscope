"""Content fingerprints invalidate cached extraction after parser changes."""
import hashlib
from pathlib import Path


def parser_version(family):
    files = ['trreb_parser_version.py', 'pilot_trreb.py', 'trreb_history.py']
    if family in {'rental', 'resale_annual'}:
        files += ['trreb_tables.py', 'trreb_rental.py' if family == 'rental' else 'trreb_annual.py']
    elif family != 'resale':
        raise ValueError(f'Unsupported report family: {family}')
    digest = hashlib.sha256()
    for name in files:
        digest.update(name.encode())
        digest.update((Path(__file__).parent / name).read_bytes())
    return digest.hexdigest()
