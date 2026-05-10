from app.models import ETLRun, Geography, Metric


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
