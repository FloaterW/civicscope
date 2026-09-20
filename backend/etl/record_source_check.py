"""Record a reviewed, unchanged candidate without replacing published data.

The output is a review artifact, not an automatic production promotion.
"""
import argparse
import csv
import json
from datetime import datetime, UTC
from pathlib import Path

from etl.refresh_candidate import ARTIFACTS, digest
from app.services.refresh_provenance import packaged_digest


def equivalent(name, published, candidate):
    if published.read_bytes() == candidate.read_bytes():
        return True
    if name == "cmhc_seed.json":
        left, right = [json.loads(p.read_text(encoding="utf-8")) for p in (published, candidate)]
        # Fetch timestamps and coverage diagnostics are not observed values.
        for value in (left, right):
            value["metadata"] = {k: v for k, v in value["metadata"].items() if k not in ("fetched_at", "coverage")}
            value["metrics"] = sorted(value["metrics"], key=lambda row: (row["geoid"], row["year"]))
        return left == right
    if name.endswith(".csv"):
        def rows(path):
            with path.open(encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                return reader.fieldnames, sorted(json.dumps(row, sort_keys=True) for row in reader)
        return rows(published) == rows(candidate)
    return False


def record_check(source, published, candidate):
    evidence = json.loads((candidate / "refresh_manifest.json").read_text(encoding="utf-8"))["sources"][source]
    timestamp = datetime.fromisoformat(evidence["last_checked_at"].replace("Z", "+00:00"))
    if timestamp.tzinfo is None or timestamp > datetime.now(UTC):
        raise ValueError("Candidate needs a valid, non-future source check timestamp")
    artifacts = {}
    for name in ARTIFACTS[source]:
        actual = digest(candidate / name)
        if evidence["artifacts"][name]["sha256"] != actual:
            raise ValueError(f"Candidate hash mismatch: {name}")
        if not equivalent(name, published / name, candidate / name):
            raise ValueError(f"Candidate changes published data: {name}; review and promote data separately")
        artifacts[name] = {"sha256": packaged_digest(published / name), "candidate_sha256": actual}
    existing = published / "refresh_manifest.json"
    manifest = json.loads(existing.read_text(encoding="utf-8")) if existing.exists() else {"schema_version": 1, "sources": {}}
    manifest["sources"][source] = {"last_checked_at": evidence["last_checked_at"], "artifacts": artifacts}
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=ARTIFACTS, required=True)
    parser.add_argument("--published", type=Path, default=Path("app/data"))
    parser.add_argument("--candidate", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(record_check(args.source, args.published, args.candidate), indent=2))
