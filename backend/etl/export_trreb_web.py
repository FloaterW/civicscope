"""Export only owner-approved municipal aggregates for the public web archive.

Source PDFs, staging databases, rental tables and private release manifests are
never exported. Run after preparing and separately approving a release bundle.
"""
import argparse
import hashlib
import json
from pathlib import Path

from etl.trreb_release import validate_release


def public_archive(release, approved_release):
    validate_release(release)
    if release['release_id'] != approved_release:
        raise ValueError('Release does not match the separately approved SHA')
    return {
        'schema_version': 1,
        'source_release': release['release_id'],
        'observations': release['observations'],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--approved-release', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    archive = public_archive(json.loads(args.bundle.read_text(encoding='utf-8')), args.approved_release)
    # Compact one-row-per-line JSON keeps the public artifact reviewable.
    rows = ',\n'.join(json.dumps(row, ensure_ascii=False, separators=(',', ':')) for row in archive['observations'])
    text = ('{"schema_version":1,"source_release":' + json.dumps(archive['source_release'])
            + ',"observations":[\n' + rows + '\n]}\n')
    with args.output.open('x', encoding='utf-8', newline='\n') as output:
        output.write(text)
    print(json.dumps({'observations': len(archive['observations']),
                      'file_sha256': hashlib.sha256(text.encode()).hexdigest()}))


if __name__ == '__main__':
    main()
