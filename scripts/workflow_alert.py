"""Maintain one GitHub issue per operational incident, without repeated comments."""
import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path


def gh(*args):
    return subprocess.check_output(["gh", *args], text=True)


def alert(title, failed):
    repo = os.environ["GITHUB_REPOSITORY"]
    issues = json.loads(gh("issue", "list", "--repo", repo, "--state", "open", "--search", f'"{title}" in:title', "--json", "number,title,author", "--limit", "100"))
    existing = next((issue for issue in issues if issue["title"] == title and issue["author"]["login"] == "github-actions[bot]"), None)
    if failed and not existing:
        url = f"https://github.com/{repo}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
        with tempfile.TemporaryDirectory() as directory:
            body = Path(directory) / "body.md"
            body.write_text(f"An operational check failed. Inspect the [workflow run]({url}) for the affected source or endpoint.\n\nThe previous deployed data remains in service. This issue is closed automatically after recovery.\n", encoding="utf-8")
            gh("issue", "create", "--repo", repo, "--title", title, "--body-file", str(body))
    elif not failed and existing:
        gh("issue", "close", str(existing["number"]), "--repo", repo, "--reason", "completed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--title", required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args()
    alert(args.title, args.result != "success")
