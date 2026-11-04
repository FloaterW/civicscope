"""Bounded production smoke checks; reports warm-up separately from downtime."""
import argparse
import json
import math
import os
import time
import urllib.request
from urllib.error import HTTPError


def read(url):
    start = time.monotonic()
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "CivicScope-health-check"}), timeout=75) as response:
        body = response.read(2_000_001)
        if len(body) > 2_000_000:
            raise ValueError("Response exceeds monitor size limit")
        return body, time.monotonic() - start


def check(api, frontend):
    results = []
    for label, url in [("api_health", api + "/health"), ("frontend", frontend), ("data", api + "/api/summary?type=municipality"), ("freshness", api + "/api/data-status"), ("trreb_archive", frontend + "/api/trreb-archive/resale/3520005?year=2025")]:
        error = None
        http_status = None
        started = time.monotonic()
        for attempt in range(2):
            try:
                body, seconds = read(url)
                if label != "frontend":
                    payload = json.loads(body)
                    if label == "api_health" and payload.get("status") != "ok":
                        raise ValueError("Database health is degraded")
                    if label == "data" and not payload.get("population"):
                        raise ValueError("Summary has no population data")
                    if label == "freshness" and payload.get("geography_count") != 1359:
                        raise ValueError("Expected 25 municipalities and 1,334 tracts")
                    if label == "trreb_archive":
                        if (payload.get("geoid") != "3520005" or payload.get("period") != "2025"
                                or payload.get("preview_only") is not False
                                or not payload.get("source_sha256") or not payload.get("archive_sha256")
                                or type(payload.get("median_price")) not in (int, float)
                                or not math.isfinite(payload["median_price"])
                                or payload["median_price"] <= 0
                                or type(payload.get("sales")) is not int or payload["sales"] < 0
                                or type(payload.get("property_days")) not in (int, float)
                                or not math.isfinite(payload["property_days"])
                                or payload["property_days"] < 0):
                            raise ValueError("Invalid public TRREB archive response")
                elif b"CivicScope" not in body:
                    raise ValueError("Frontend content is missing")
                result = {"check": label, "seconds": round(seconds, 3), "retried": bool(attempt), "slow": seconds > 5}
                result["total_seconds"] = round(time.monotonic() - started, 3)
                if label == "freshness":
                    sources = {source.get("source"): source for source in payload.get("sources", []) if isinstance(source, dict)}
                    result["source_checks"] = [{"source": name, "status": sources.get(name, {}).get("check_status", "unknown"), "coverage": sources.get(name, {}).get("coverage")} for name in ("census", "cmhc", "transit")]
                    result["freshness_warning"] = any(source["status"] != "checked" for source in result["source_checks"])
                results.append(result)
                error = None
                break
            except Exception as exc:
                error = type(exc).__name__
                http_status = exc.code if isinstance(exc, HTTPError) else None
                if attempt == 0:
                    time.sleep(5)
        if error:
            failure = {"check": label, "error": error, "attempts": 2, "total_seconds": round(time.monotonic() - started, 3)}
            if http_status is not None:
                failure["http_status"] = http_status
            results.append(failure)
    return results


def report(results):
    """Separate availability failures from a deduplicated data-verification incident."""
    availability_failed = any("error" in result for result in results)
    freshness = next((result for result in results if result["check"] == "freshness"), {})
    # An unavailable API cannot establish recovery of a previous freshness incident.
    freshness_result = "unknown" if not freshness or "error" in freshness else "failure" if freshness.get("freshness_warning") else "success"
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as stream:
            stream.write(f"freshness_result={freshness_result}\n")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write("## CivicScope production checks\n\n")
            for result in results:
                state = "FAILED" if "error" in result else "SLOW" if result.get("slow") else "OK"
                stream.write(f"- {result['check']}: {state}; {result.get('total_seconds', 0)} seconds total\n")
            stream.write(f"\nSource verification: {freshness_result}. See structured log for source details.\n")
    return int(availability_failed)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="https://civicscope.onrender.com")
    parser.add_argument("--frontend", default="https://civicscope-gold.vercel.app")
    args = parser.parse_args()
    results = check(args.api.rstrip("/"), args.frontend.rstrip("/"))
    print(json.dumps(results, indent=2))
    raise SystemExit(report(results))
