from app.models import Geography, Metric
from app.services.seed import load_transit_scores, seed_transit_scores
from etl.load_transit import normalize_route_counts


def test_normalize_route_counts_keeps_zero_service_tracts():
    scores = normalize_route_counts({"zero": 0, "low": 2, "high": 20})

    assert set(scores) == {"zero", "low", "high"}
    assert scores["zero"] == (0, 0.0)
    assert scores["high"][1] == 100.0


def test_seed_transit_scores_fills_unlisted_tracts_with_zero(db_session):
    packaged_geoids = {row["geoid"] for row in load_transit_scores()}
    missing = (
        db_session.query(Metric)
        .join(Geography, Geography.geoid == Metric.geoid)
        .filter(Geography.type == "census_tract", ~Metric.geoid.in_(packaged_geoids))
        .first()
    )
    assert missing is not None, "fixture should include at least one zero-service tract"

    updated = seed_transit_scores(db_session)
    db_session.refresh(missing)

    assert updated == 1334
    assert missing.transit_route_count == 0
    assert missing.transit_score == 0.0


def test_seed_transit_scores_repairs_stale_values(db_session):
    seed_transit_scores(db_session)
    target = db_session.query(Metric).filter(Metric.transit_route_count.isnot(None)).first()
    assert target is not None
    expected_count = target.transit_route_count
    expected_score = target.transit_score
    target.transit_route_count = 999
    target.transit_score = 99.9
    db_session.commit()

    updated = seed_transit_scores(db_session)
    db_session.refresh(target)

    assert updated == 1334
    assert target.transit_route_count == expected_count
    assert target.transit_score == expected_score
