import pytest

from backend.economy.db import connect, init_schema
from backend.economy.repository import OsmObjectRepository


@pytest.fixture
def con():
    con = connect(":memory:")
    init_schema(con)
    insert_object(con, "node", 1, '{"amenity": "bank", "name": "Банк"}',
                  '{"type": "Point", "coordinates": [39.9, 57.6]}')
    insert_object(con, "node", 2, '{"place": "village", "name": "Заречье"}',
                  '{"type": "Point", "coordinates": [40.1, 57.7]}')
    insert_object(con, "node", 3, '{"highway": "bus_stop"}',
                  '{"type": "Point", "coordinates": [39.8, 57.5]}')
    classify(con, "node", 1, "money", "supply", "bank")
    classify(con, "node", 2, "money", "demand", "settlement")
    classify(con, "node", 2, "labor", "supply", "settlement")
    return con


def insert_object(con, osm_type, osm_id, tags, geojson):
    con.execute(
        "INSERT INTO osm_objects (osm_type, osm_id, tags, geom, region) "
        "VALUES (?, ?, ?, ST_GeomFromGeoJSON(?), 'yaroslavl')",
        [osm_type, osm_id, tags, geojson])


def classify(con, osm_type, osm_id, domain, role, kind):
    con.execute(
        "INSERT INTO osm_classification (osm_type, osm_id, domain, role, kind) "
        "VALUES (?, ?, ?, ?, ?)", [osm_type, osm_id, domain, role, kind])


def test_reads_tags_geometry_and_classification(con):
    objects = OsmObjectRepository(con).find_all()

    assert len(objects) == 3

    bank = objects[0]
    assert bank.tags["amenity"] == "bank"
    assert bank.geometry["type"] == "Point"
    assert bank.kind == "bank"
    assert len(bank.roles) == 1

    village = objects[1]
    assert {r.domain for r in village.roles} == {"money", "labor"}

    assert objects[2].kind is None      # не классифицирован
    assert objects[2].roles == []


def test_filters_by_region(con):
    repo = OsmObjectRepository(con)
    assert len(repo.find_by_region("yaroslavl")) == 3
    assert repo.find_by_region("other") == []