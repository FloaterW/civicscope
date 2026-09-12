"""Refresh an isolated copy; export validated candidates, never write the live DB."""
import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = {
    "census": ["demo_seed.json", "statcan_ct_metrics.csv"],
    "cmhc": ["cmhc_seed.json", "cmhc_ct_metrics.csv"],
    "transit": ["transit_scores.csv", "transit_routes.geojson", "transit_manifest.json"],
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_candidate(source, before, after):
    seed = json.loads((after / "demo_seed.json").read_text(encoding="utf-8"))
    baseline = json.loads((before / "demo_seed.json").read_text(encoding="utf-8"))
    if {g["geoid"] for g in seed["geographies"]} != {g["geoid"] for g in baseline["geographies"]}:
        raise ValueError("Candidate changed the supported geography set")
    for name in ARTIFACTS[source]:
        if not (after / name).is_file() or (after / name).stat().st_size == 0:
            raise ValueError(f"Missing candidate artifact: {name}")
    if source == "cmhc":
        old = json.loads((before / "cmhc_seed.json").read_text(encoding="utf-8"))
        new = json.loads((after / "cmhc_seed.json").read_text(encoding="utf-8"))
        if not set(old["metadata"]["years"]).issubset(new["metadata"]["years"]):
            raise ValueError("Candidate removed supported CMHC years")
        if new["metadata"].get("coverage", {}).get("partial"):
            raise ValueError("Partial CMHC refresh cannot be published")
    if source == "transit":
        manifest = json.loads((after / "transit_manifest.json").read_text(encoding="utf-8"))
        if manifest.get("coverage_status") != "complete":
            raise ValueError("Incomplete transit agency coverage")
        with (after / "transit_scores.csv").open(encoding="utf-8", newline="") as handle:
            score_ids = [row["geoid"] for row in csv.DictReader(handle)]
        tracts = {g["geoid"] for g in seed["geographies"] if g["type"] == "census_tract"}
        if set(score_ids) != tracts or len(score_ids) != len(tracts):
            raise ValueError("Transit refresh must cover every supported tract exactly once")
        routes = json.loads((after / "transit_routes.geojson").read_text(encoding="utf-8"))
        agencies = {f["properties"]["agency_id"] for f in routes["features"]}
        if agencies != {agency["id"] for agency in manifest["included_agencies"]}:
            raise ValueError("Transit scores and overlay have different agency coverage")
        for name in ("transit_scores.csv", "transit_routes.geojson"):
            if manifest["artifacts"][name]["sha256"] != digest(after / name):
                raise ValueError(f"Manifest hash mismatch: {name}")


def refresh(source, output):
    if output.exists():
        raise ValueError("Use a new candidate directory; existing data will not be overwritten")
    with tempfile.TemporaryDirectory(prefix="civicscope-refresh-") as temporary:
        stage = Path(temporary) / "backend"
        # Copy only application inputs/code. Never copy .env files or databases.
        for directory in ("app", "etl", "alembic"):
            shutil.copytree(ROOT / directory, stage / directory, ignore=shutil.ignore_patterns("__pycache__", "gtfs_cache", "*.db", "*.log"))
        shutil.copy2(ROOT / "alembic.ini", stage / "alembic.ini")
        env = dict(os.environ)
        env.update(APP_ENV="development", DATABASE_URL=f"sqlite:///{stage / 'refresh.db'}", SEED_ON_STARTUP="false")
        def run(*args, transit=False):
            process_env = dict(env)
            if transit:
                # This URL must target the disposable PostGIS service provisioned
                # by the workflow, never the production connection string.
                url = os.environ.get("REFRESH_POSTGIS_URL", "")
                parsed = urlsplit(url)
                if parsed.scheme != "postgresql+psycopg" or parsed.hostname != "127.0.0.1" or parsed.username != "refresh" or parsed.path != "/refresh":
                    raise ValueError("Transit requires a disposable local REFRESH_POSTGIS_URL")
                process_env["DATABASE_URL"] = url
            subprocess.run([sys.executable, *args], cwd=stage, env=process_env, check=True, timeout=3600)
        if source == "census":
            run("etl/load_census.py", "--update-seed")
            run("etl/load_tract_census.py", "--generate-csv", "--update-seed")
        elif source == "cmhc":
            run("etl/load_cmhc.py", "--update-seed")
            with (ROOT / "app/data/cmhc_ct_metrics.csv").open(encoding="utf-8", newline="") as handle:
                years = sorted({row["year"] for row in csv.DictReader(handle)})
            run("etl/load_cmhc_tracts.py", "--generate-csv", "--years", *years)
        else:
            run("-m", "alembic", "upgrade", "head", transit=True)
            run("etl/seed_demo_data.py", transit=True)
            run("etl/load_transit.py", "--refresh", "--generate-csv", "--routes-output", str(stage / "app/data/transit_routes.geojson"), transit=True)
        before, after = ROOT / "app/data", stage / "app/data"
        validate_candidate(source, before, after)
        manifest_path = before / "refresh_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"schema_version": 1, "sources": {}}
        manifest["sources"][source] = {
            "last_checked_at": datetime.now(UTC).isoformat(),
            "artifacts": {name: {"sha256": digest(after / name), "changed": digest(before / name) != digest(after / name)} for name in ARTIFACTS[source]},
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".candidate-", dir=output.parent) as publishing:
            candidate = Path(publishing) / "data"
            candidate.mkdir()
            for name in ARTIFACTS[source]:
                shutil.copy2(after / name, candidate / name)
            (candidate / "refresh_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            candidate.rename(output)
        print(f"Validated {source} candidate saved to {output}. Review and deploy these artifacts together.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=ARTIFACTS, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    refresh(args.source, args.output.resolve())
