"""Fail the stable required CI check unless all split jobs have succeeded."""

import json
import os
import sys


REQUIRED_JOBS = frozenset({
    "dependency-review", "backend-tests", "windows-locks", "frontend-checks", "browsers", "postgis", "containers",
})


def validate_results(results, event_name):
    if event_name not in {"pull_request", "push"}:
        return [f"Unexpected CI event: {event_name!r}"]
    if not isinstance(results, dict) or set(results) != REQUIRED_JOBS:
        return ["CI job results do not match the complete required job set"]
    failures = []
    for name in sorted(REQUIRED_JOBS):
        job = results[name]
        outcome = job.get("result") if isinstance(job, dict) else None
        expected = "skipped" if name == "dependency-review" and event_name == "push" else "success"
        if outcome != expected:
            failures.append(f"{name}: expected {expected}, received {outcome!r}")
    return failures


def main():
    try:
        results = json.loads(os.environ.get("CI_JOB_RESULTS", ""))
    except json.JSONDecodeError:
        print("Missing or invalid CI_JOB_RESULTS", file=sys.stderr)
        return 1
    failures = validate_results(results, os.environ.get("GITHUB_EVENT_NAME"))
    if failures:
        print("Required CI validation failed:\n" + "\n".join(failures), file=sys.stderr)
        return 1
    print("All required split jobs passed; event-specific dependency review is satisfied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
