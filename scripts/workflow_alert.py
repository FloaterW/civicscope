"""Maintain one GitHub issue per operational incident, without repeated comments."""
import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

SOURCES = ("census", "cmhc", "transit")
LEGACY_SOURCE_TITLE = "Source verification overdue or unknown"
AUTOMATION_AUTHORS = {"github-actions[bot]", "app/github-actions"}


def gh(*args):
    return subprocess.check_output(["gh", *args], text=True)


def existing_incident(title):
    repo = os.environ["GITHUB_REPOSITORY"]
    issues = json.loads(gh("issue", "list", "--repo", repo, "--state", "open", "--search", f'"{title}" in:title', "--json", "number,title,author", "--limit", "100"))
    # gh's GraphQL output may represent a Bot as app/github-actions, while
    # REST output uses github-actions[bot]. Neither is a human account name.
    return next((issue for issue in issues if issue["title"] == title and issue["author"]["login"] in AUTOMATION_AUTHORS), None)


def alert(title, failed):
    repo = os.environ["GITHUB_REPOSITORY"]
    existing = existing_incident(title)
    if failed and not existing:
        url = f"https://github.com/{repo}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
        with tempfile.TemporaryDirectory() as directory:
            body = Path(directory) / "body.md"
            body.write_text(f"An operational check failed. Inspect the [workflow run]({url}) for the affected source or endpoint.\n\nThe previous deployed data remains in service. This issue is closed automatically after recovery.\n", encoding="utf-8")
            created_url = gh("issue", "create", "--repo", repo, "--title", title, "--body-file", str(body)).strip()
        prefix = f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com').rstrip('/')}/{repo}/issues/"
        if not created_url.startswith(prefix) or not created_url.removeprefix(prefix).isdigit():
            raise RuntimeError("Created incident was not confirmed")
        # Search indexing can lag creation. Read the returned issue directly so
        # safe legacy migration does not produce a spurious monitor failure.
        created = json.loads(gh("issue", "view", created_url, "--repo", repo, "--json", "number,title,author,state"))
        if (created.get("title") != title or created.get("state") != "OPEN"
                or created.get("author", {}).get("login") not in AUTOMATION_AUTHORS
                or str(created.get("number")) != created_url.removeprefix(prefix)):
            raise RuntimeError("Created incident was not confirmed")
        return created
    elif failed:
        return existing
    elif not failed and existing:
        gh("issue", "close", str(existing["number"]), "--repo", repo, "--reason", "completed")


def source_alerts(states):
    """Reconcile sources separately, then retire the legacy combined incident.

    Endpoint unavailability is unknown, not recovery. A known unknown/overdue
    source is a failure and gets its own incident. Verify replacement incidents
    exist before retiring the combined issue, including after a partial run.
    """
    if not isinstance(states, dict) or set(states) != set(SOURCES) or any(
        value not in ("success", "failure", "unknown") for value in states.values()
    ):
        raise ValueError("Expected exactly census/cmhc/transit source results")
    confirmed = {}
    for source in SOURCES:
        state = states[source]
        if state != "unknown":
            confirmed[source] = alert(f"Source verification - {source}", state == "failure")
    if "unknown" in states.values():
        return
    for source in SOURCES:
        if states[source] == "failure" and not confirmed.get(source):
            raise RuntimeError("Replacement source incident was not confirmed; keeping legacy incident")
    alert(LEGACY_SOURCE_TITLE, False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--title")
    parser.add_argument("--result")
    parser.add_argument("--sources", action="store_true", help="Read per-source states from SOURCE_RESULTS")
    args = parser.parse_args()
    if args.sources:
        if args.title or args.result:
            parser.error("--sources cannot be combined with --title or --result")
        source_alerts(json.loads(os.environ["SOURCE_RESULTS"]))
    elif args.title and args.result:
        alert(args.title, args.result != "success")
    else:
        parser.error("Provide --sources, or both --title and --result")
