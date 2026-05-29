from app.models import ETLRun, Geography, Metric
from app.services.seed import load_demo_seed, seed_demo_data


def test_seed_data_loaded(db_session):
    assert db_session.query(Geography).count() >= 6
    assert db_session.query(Metric).count() >= 6
    assert db_session.query(ETLRun).filter(ETLRun.status == "success").count() == 1
    assert db_session.query(Geography).filter(Geography.geoid == "3520005").one().state == "ON"
    assert db_session.query(Geography).filter(Geography.type == "census_tract").count() > 1000


def test_seed_geographies_have_geojson(db_session):
    geography = db_session.query(Geography).first()
    assert geography.geometry["type"] in {"Polygon", "MultiPolygon"}
    assert len(geography.bbox) == 4


def test_reseed_skipped_when_db_matches_seed(db_session):
    # The fixture already seeded once; an identical second call is a no-op so
    # that healthy databases are not needlessly re-seeded on every startup.
    assert seed_demo_data(db_session) == 0


def test_reseed_triggers_when_db_content_is_stale(db_session):
    # Simulate the stale-volume bug: a geography's metric in the DB no longer
    # matches the packaged official seed value.
    seed = load_demo_seed()
    target = seed["geographies"][0]
    geoid = target["geoid"]
    year = target["metrics"][0]["year"]
    official_income = target["metrics"][0]["median_income"]

    metric = (
        db_session.query(Metric).filter(Metric.geoid == geoid, Metric.year == year).one()
    )
    metric.median_income = (official_income or 0) + 50000
    db_session.commit()

    reseeded = seed_demo_data(db_session)
    assert reseeded > 0

    restored = (
        db_session.query(Metric).filter(Metric.geoid == geoid, Metric.year == year).one()
    )
    assert restored.median_income == official_income


def test_seed_does_not_bake_estimated_rent_burden_into_db(db_session):
    # Census tracts whose official rent burden is suppressed must remain NULL in
    # the database; estimation is a clearly-labeled serialization-time fallback,
    # never silently persisted as if it were official.
    seed = load_demo_seed()
    target = next(
        geo
        for geo in seed["geographies"]
        if geo["type"] == "census_tract"
        and geo["metrics"][0].get("rent_burden_pct") is None
        and geo["metrics"][0].get("median_rent") is not None
        and geo["metrics"][0].get("median_income") is not None
    )
    metric = (
        db_session.query(Metric).filter(Metric.geoid == target["geoid"]).one()
    )
    assert metric.rent_burden_pct is None
