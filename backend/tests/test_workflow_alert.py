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


@pytest.fixture
def source_incidents(monkeypatch):
    spec = importlib.util.spec_from_file_location("source_alert_test", Path(__file__).resolve().parents[2] / "scripts/workflow_alert.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("GITHUB_REPOSITORY", "example/civicscope")
    monkeypatch.setenv("GITHUB_RUN_ID", "123")
    issues = [{"number": 1, "title": module.LEGACY_SOURCE_TITLE, "author": {"login": "github-actions[bot]"}}]
    events = []

    def gh(*args):
        operation = args[1]
        if operation == "list":
            title = args[args.index("--search") + 1].split('"')[1]
            return json.dumps([issue for issue in issues if issue["title"] == title])
        if operation == "create":
            title = args[args.index("--title") + 1]
            number = max((issue["number"] for issue in issues), default=0) + 1
            issues.append({"number": number, "title": title, "author": {"login": "github-actions[bot]"}})
            events.append(("create", title))
            return f"https://github.com/example/civicscope/issues/{number}"
        if operation == "view":
            number = int(args[2].rsplit("/", 1)[-1])
            return json.dumps({**next(issue for issue in issues if issue["number"] == number), "state": "OPEN"})
        assert operation == "close"
        issue = next(issue for issue in issues if str(issue["number"]) == args[2])
        events.append(("close", issue["title"]))
        issues.remove(issue)
        return ""

    monkeypatch.setattr(module, "gh", gh)
    return module, issues, events


def test_new_source_failure_not_hidden_by_existing_transit_incident(source_incidents):
    module, issues, events = source_incidents
    state = {"census": "success", "cmhc": "success", "transit": "failure"}
    module.source_alerts(state)
    assert events == [("create", "Source verification - transit"), ("close", module.LEGACY_SOURCE_TITLE)]
    module.source_alerts(state)
    assert len(events) == 2  # identical failures do not generate repeated notifications
    module.source_alerts({**state, "cmhc": "failure"})
    assert events[-1] == ("create", "Source verification - cmhc")
    module.source_alerts(state)
    assert events[-1] == ("close", "Source verification - cmhc")
    assert [issue["title"] for issue in issues] == ["Source verification - transit"]


def test_endpoint_unavailability_never_resolves_source_or_legacy_incidents(source_incidents):
    module, issues, events = source_incidents
    module.source_alerts(dict.fromkeys(module.SOURCES, "unknown"))
    assert events == []
    assert issues[0]["title"] == module.LEGACY_SOURCE_TITLE


def test_partial_unknown_does_not_retire_legacy_incident(source_incidents):
    module, issues, events = source_incidents
    module.source_alerts({"census": "success", "cmhc": "unknown", "transit": "failure"})
    assert events == [("create", "Source verification - transit")]
    assert any(issue["title"] == module.LEGACY_SOURCE_TITLE for issue in issues)


def test_failed_replacement_creation_preserves_legacy_incident(source_incidents, monkeypatch):
    module, issues, events = source_incidents
    original = module.gh

    def fail_create(*args):
        if args[1] == "create":
            raise RuntimeError("GitHub unavailable")
        return original(*args)

    monkeypatch.setattr(module, "gh", fail_create)
    with pytest.raises(RuntimeError, match="GitHub unavailable"):
        module.source_alerts({"census": "success", "cmhc": "success", "transit": "failure"})
    assert events == []
    assert issues[0]["title"] == module.LEGACY_SOURCE_TITLE


def test_unconfirmed_replacement_preserves_legacy_incident(source_incidents, monkeypatch):
    module, issues, events = source_incidents
    original = module.gh
    monkeypatch.setattr(module, "gh", lambda *args: "" if args[1] == "create" else original(*args))
    with pytest.raises(RuntimeError, match="not confirmed"):
        module.source_alerts({"census": "success", "cmhc": "success", "transit": "failure"})
    assert issues[0]["title"] == module.LEGACY_SOURCE_TITLE


def test_new_incident_confirmation_does_not_depend_on_search_indexing(source_incidents, monkeypatch):
    module, issues, events = source_incidents
    original = module.gh

    def delayed_search(*args):
        response = original(*args)
        if args[1] == "list":
            return json.dumps([issue for issue in json.loads(response) if issue["number"] == 1])
        return response

    monkeypatch.setattr(module, "gh", delayed_search)
    module.source_alerts({"census": "success", "cmhc": "success", "transit": "failure"})
    assert events == [("create", "Source verification - transit"), ("close", module.LEGACY_SOURCE_TITLE)]


@pytest.mark.parametrize("change", [{"title": "Wrong incident"}, {"state": "CLOSED"}, {"author": {"login": "resident"}}, {"number": 999}])
def test_direct_issue_confirmation_must_match_open_automation_incident(source_incidents, monkeypatch, change):
    module, issues, events = source_incidents
    original = module.gh

    def invalid_confirmation(*args):
        response = original(*args)
        return json.dumps({**json.loads(response), **change}) if args[1] == "view" else response

    monkeypatch.setattr(module, "gh", invalid_confirmation)
    with pytest.raises(RuntimeError, match="not confirmed"):
        module.source_alerts({"census": "success", "cmhc": "success", "transit": "failure"})
    assert any(issue["title"] == module.LEGACY_SOURCE_TITLE for issue in issues)


@pytest.mark.parametrize("states", [None, {}, {"census": "success"}, {"census": "success", "cmhc": "failure", "transit": True}])
def test_bad_source_results_do_not_mutate_issues(source_incidents, states):
    module, issues, events = source_incidents
    with pytest.raises(ValueError, match="exactly"):
        module.source_alerts(states)
    assert events == []
