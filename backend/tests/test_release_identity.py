import pytest

from app.core.release import release_commit


@pytest.mark.parametrize("value", ["", "main", "a" * 7, "g" * 40, "a" * 40 + "\n", "private-token"])
def test_release_identity_never_echoes_invalid_environment(monkeypatch, value):
    monkeypatch.setenv("RENDER_GIT_COMMIT", value)
    monkeypatch.setenv("CIVICSCOPE_BUILD_SHA", "b" * 40)
    assert release_commit() is None


def test_provider_commit_wins_over_local_fallback(monkeypatch):
    monkeypatch.setenv("RENDER_GIT_COMMIT", "A" * 40)
    monkeypatch.setenv("CIVICSCOPE_BUILD_SHA", "b" * 40)
    assert release_commit() == "a" * 40


def test_local_release_or_explicit_unknown(monkeypatch):
    monkeypatch.delenv("RENDER_GIT_COMMIT", raising=False)
    monkeypatch.delenv("CIVICSCOPE_BUILD_SHA", raising=False)
    assert release_commit() is None
    monkeypatch.setenv("CIVICSCOPE_BUILD_SHA", "c" * 40)
    assert release_commit() == "c" * 40


def test_health_release_is_uncached_and_preserved_on_database_failure(client, db_session, monkeypatch):
    monkeypatch.setenv("RENDER_GIT_COMMIT", "a" * 40)
    healthy = client.get("/health")
    assert healthy.status_code == 200
    assert healthy.json()["commit"] == "a" * 40
    assert healthy.headers["cache-control"] == "no-store"

    def unavailable(_statement):
        raise RuntimeError("private database details")

    monkeypatch.setattr(db_session, "execute", unavailable)
    failed = client.get("/health")
    assert failed.status_code == 503
    assert failed.json() == {"status": "degraded", "service": "civicscope-api", "database": "unavailable", "commit": "a" * 40}
    assert failed.headers["cache-control"] == "no-store"
