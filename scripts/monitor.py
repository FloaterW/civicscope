"""Bounded production smoke checks; reports warm-up separately from downtime."""
import argparse
import json
import time
import urllib.request


def read(url):
    start = time.monotonic()
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "CivicScope-health-check"}), timeout=75) as response:
        body = response.read(2_000_001)
        if len(body) > 2_000_000:
            raise ValueError("Response exceeds monitor size limit")
        return body, time.monotonic() - start


def check(api, frontend):
    results = []
    for label, url in [("api_health", api + "/health"), ("frontend", frontend), ("data", api + "/api/summary?type=municipality"), ("freshness", api + "/api/data-status")]:
        error = None
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
                elif b"CivicScope" not in body:
                    raise ValueError("Frontend content is missing")
                result = {"check": label, "seconds": round(seconds, 3), "retried": bool(attempt), "slow": seconds > 5}
                if label == "freshness":
                    result["source_checks"] = [{"source": source.get("source"), "status": source.get("check_status", "unknown"), "coverage": source.get("coverage")} for source in payload.get("sources", [])]
                results.append(result)
                error = None
                break
            except Exception as exc:
                error = type(exc).__name__
                if attempt == 0:
                    time.sleep(5)
        if error:
            results.append({"check": label, "error": error})
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="https://civicscope.onrender.com")
    parser.add_argument("--frontend", default="https://civicscope-gold.vercel.app")
    args = parser.parse_args()
    results = check(args.api.rstrip("/"), args.frontend.rstrip("/"))
    print(json.dumps(results, indent=2))
    raise SystemExit(int(any("error" in result for result in results)))
