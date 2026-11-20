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
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ARTIFACTS = {
    "census": ["demo_seed.json", "statcan_ct_metrics.csv"],
    "cmhc": ["cmhc_seed.json", "cmhc_ct_metrics.csv"],
    "transit": ["transit_scores.csv", "transit_routes.geojson", "transit_manifest.json"],
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cmhc_tract_cells(path):
    """Nonempty supported cells, including genuine zeros, not a year cross-product."""
    cells = set()
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            for metric in ("housing_starts_total", "housing_completions"):
                value = row.get(metric, "").strip()
                if value:
                    if not value.isdigit():
                        raise ValueError(f"Invalid CMHC tract count: {metric}")
                    cells.add((row["geoid"], int(row["year"]), metric))
    if not cells or {cell[2] for cell in cells} != {"housing_starts_total", "housing_completions"}:
        raise ValueError("CMHC tract baseline must include both supported metrics")
    return cells


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
        missing = cmhc_tract_cells(before / "cmhc_ct_metrics.csv") - cmhc_tract_cells(after / "cmhc_ct_metrics.csv")
        if missing:
            raise ValueError(f"Candidate removed {len(missing)} supported CMHC tract cells")
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


def retain_transit_inputs(after, candidate):
    """Keep the exact public GTFS archives used by this isolated computation."""
    from etl.load_transit import GTFS_FEEDS

    manifest = json.loads((after / "transit_manifest.json").read_text(encoding="utf-8"))
    evidence = {}
    destination = candidate / "source-inputs"
    destination.mkdir()
    for agency in manifest["included_agencies"]:
        name = agency["id"]
        if name not in GTFS_FEEDS:
            raise ValueError("Unexpected transit agency in source evidence")
        source = after / "gtfs_cache" / f"{name}.zip"
        if not source.is_file() or digest(source) != agency.get("feed_sha256"):
            raise ValueError(f"Exact GTFS input is missing or changed: {name}")
        shutil.copy2(source, destination / source.name)
        evidence[f"source-inputs/{source.name}"] = {
            "sha256": digest(source), "source_url": GTFS_FEEDS[name],
            "retrieved_at": agency.get("feed_retrieved_at"),
        }
    return evidence


def save_diagnostics(destination, state, stage):
    """Publish bounded metadata only; never copy subprocess logs, env or bodies."""
    if destination is None:
        return
    events = stage / "refresh-events.jsonl"
    records = []
    if events.exists():
        # Only our bounded retry helper writes this file. Restrict its fields as
        # a second boundary before uploading it alongside the run summary.
        allowed = {"at", "dataset", "request_sha256", "attempt", "outcome", "error_type",
                   "http_status", "retry_delay_seconds", "bytes"}
        for line in events.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            records.append({key: value for key, value in record.items() if key in allowed})
    state["finished_at"] = datetime.now(UTC).isoformat()
    state["staged_artifacts"] = {
        name: {"sha256": digest(stage / "app/data" / name), "bytes": (stage / "app/data" / name).stat().st_size}
        for name in ARTIFACTS[state["source"]] if (stage / "app/data" / name).is_file()
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".diagnostics-", dir=destination.parent) as temporary:
        content = Path(temporary) / "data"
        content.mkdir()
        (content / "refresh-diagnostics.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        (content / "fetch-events.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
        content.rename(destination)


def refresh(source, output, diagnostics=None):
    if output.exists():
        raise ValueError("Use a new candidate directory; existing data will not be overwritten")
    if diagnostics is not None and (diagnostics.exists() or diagnostics.resolve().is_relative_to(output.resolve())
                                    or output.resolve().is_relative_to(diagnostics.resolve())):
        raise ValueError("Use a new diagnostics directory separate from the candidate")
    with tempfile.TemporaryDirectory(prefix="civicscope-refresh-") as temporary:
        stage = Path(temporary) / "backend"
        # Copy only application inputs/code. Never copy .env files or databases.
        for directory in ("app", "etl", "alembic"):
            shutil.copytree(ROOT / directory, stage / directory, ignore=shutil.ignore_patterns("__pycache__", "gtfs_cache", "*.db", "*.log"))
        shutil.copy2(ROOT / "alembic.ini", stage / "alembic.ini")
        env = dict(os.environ)
        env.update(APP_ENV="development", DATABASE_URL=f"sqlite:///{stage / 'refresh.db'}", SEED_ON_STARTUP="false",
                   REFRESH_DIAGNOSTICS_FILE=str(stage / "refresh-events.jsonl"))
        state = {"source": source, "started_at": datetime.now(UTC).isoformat(), "status": "running", "steps": [],
                 "note": "Staged hashes are diagnostic only; failed or unreviewed candidates must not be promoted."}
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
            step = {"command": args[1] if args[0] == "-m" else args[0], "status": "running"}
            state["steps"].append(step)
            try:
                subprocess.run([sys.executable, *args], cwd=stage, env=process_env, check=True, timeout=3600)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
                step.update(status="failed", error_type=type(error).__name__)
                if isinstance(error, subprocess.CalledProcessError):
                    step["exit_code"] = error.returncode
                raise
            else:
                step["status"] = "success"
        try:
            if source == "census":
                run("etl/load_census.py", "--update-seed")
                run("etl/load_tract_census.py", "--generate-csv", "--update-seed")
            elif source == "cmhc":
                run("etl/load_cmhc.py", "--update-seed")
                cells = cmhc_tract_cells(ROOT / "app/data/cmhc_ct_metrics.csv")
                starts = sorted({str(year) for _, year, metric in cells if metric == "housing_starts_total"})
                completions = sorted({str(year) for _, year, metric in cells if metric == "housing_completions"})
                years = sorted(set(starts + completions))
                run("etl/load_cmhc_tracts.py", "--generate-csv", "--years", *years,
                    "--starts-years", *starts, "--completions-years", *completions)
            else:
                run("-m", "alembic", "upgrade", "head", transit=True)
                run("etl/seed_demo_data.py", transit=True)
                run("etl/load_transit.py", "--refresh", "--generate-csv", "--routes-output", str(stage / "app/data/transit_routes.geojson"), transit=True)
            before, after = ROOT / "app/data", stage / "app/data"
            state["phase"] = "validation"
            validate_candidate(source, before, after)
            manifest_path = before / "refresh_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"schema_version": 1, "sources": {}}
            manifest["sources"][source] = {
                "last_checked_at": datetime.now(UTC).isoformat(),
                "artifacts": {name: {"sha256": digest(after / name), "changed": digest(before / name) != digest(after / name)} for name in ARTIFACTS[source]},
            }
            output.parent.mkdir(parents=True, exist_ok=True)
            state["phase"] = "candidate-export"
            with tempfile.TemporaryDirectory(prefix=".candidate-", dir=output.parent) as publishing:
                candidate = Path(publishing) / "data"
                candidate.mkdir()
                for name in ARTIFACTS[source]:
                    shutil.copy2(after / name, candidate / name)
                if source == "transit":
                    evidence = retain_transit_inputs(after, candidate)
                    (candidate / "source-inputs.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
                (candidate / "refresh_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
                candidate.rename(output)
            state.update(status="validated-candidate", phase="complete")
            print(f"Validated {source} candidate saved to {output}. Independent review is required before promotion.")
        except Exception as error:
            state.update(status="failed", error_type=type(error).__name__)
            raise
        finally:
            try:
                save_diagnostics(diagnostics, state, stage)
            except Exception as diagnostic_error:
                if state["status"] != "failed":
                    raise
                # Keep the original ETL/validation exception as the failure.
                # Do not print potentially sensitive filesystem/error details.
                print(f"Unable to retain refresh diagnostics: {type(diagnostic_error).__name__}", file=sys.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=ARTIFACTS, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--diagnostics-output", type=Path, help="New directory for sanitized success/failure evidence")
    args = parser.parse_args()
    refresh(args.source, args.output.resolve(), args.diagnostics_output.resolve() if args.diagnostics_output else None)
