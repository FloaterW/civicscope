import importlib.util
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.mark.parametrize("login", ["github-actions[bot]", "app/github-actions"])
@pytest.mark.parametrize("failed", [True, False])
def test_incident_reuses_only_the_automation_issue(monkeypatch, login, failed):
    spec = importlib.util.spec_from_file_location("workflow_alert_test", Path(__file__).resolve().parents[2] / "scripts/workflow_alert.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("GITHUB_REPOSITORY", "example/civicscope")
    call = MagicMock(return_value=json.dumps([
        {"number": 1, "title": "Incident", "author": {"login": "resident"}},
        {"number": 2, "title": "Incident", "author": {"login": login}},
    ]))
    monkeypatch.setattr(module, "gh", call)
    module.alert("Incident", failed)
    if failed:
        assert call.call_count == 1  # no duplicate issue or repeated comment
    else:
        assert call.call_args.args == ("issue", "close", "2", "--repo", "example/civicscope", "--reason", "completed")
