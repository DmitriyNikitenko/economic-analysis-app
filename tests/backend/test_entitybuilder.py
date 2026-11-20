# Тесты сборщика сущностей
import json
import pytest

from backend.economy.models import Capacity, District
from backend.economy.repository import Repository
from backend.entity_builder.__main__ import (
    DEFAULT_CAPACITY,
    build_subjects,
    estimate_capacity,
    fetch_rows,
    make_address,
    make_subject_id,
)

DOMAINS = ["money", "labor"]

def row(osm_type="node", osm_id=1, tags=None, lon=39.9, lat=57.6,
        domain="money", role="demand", kind="settlement", district_id=None):
    # одна строка так, как её отдаёт fetch_rows: объект OSM в одном домене
    return (osm_type, osm_id, json.dumps(tags or {}), lon, lat, domain, role, kind, district_id)


#  make_subject_id 
@pytest.mark.parametrize("osm_type, osm_id, expected", [
    ("node", 123, "s_n123"),
    ("way", 7, "s_w7"),
    ("relation", 55, "s_r55"),
])

def test_subject_id_is_built_from_osm_id(osm_type, osm_id, expected):
    assert make_subject_id(osm_type, osm_id) == expected

def test_same_osm_id_in_different_types_gives_different_subject_ids():
    assert make_subject_id("node", 1) != make_subject_id("way", 1)

#  make_address 
@pytest.mark.parametrize("tags, expected", [
    ({"addr:street": "Лесная", "addr:housenumber": "5"}, "Лесная, 5"),
    ({"addr:street": "Лесная"}, "Лесная"),
    ({"addr:housenumber": "5"}, None),  # номер дома без улицы адресом не считаем
    ({}, None),
])

def test_address_from_tags(tags, expected):
    assert make_address(tags) == expected

#  estimate_capacity 
def test_settlement_capacity_is_population():
    assert estimate_capacity("settlement", {"population": "1200"}) == 1200.0
    assert estimate_capacity("settlement", {"population": "1200.5"}) == 1200.5

@pytest.mark.parametrize("population", ["много", "", "0", "-5", "1 200"])
def test_settlement_with_bad_population_gets_default(population):
    assert estimate_capacity("settlement", {"population": population}) == DEFAULT_CAPACITY

def test_settlement_without_population_gets_default():
    assert estimate_capacity("settlement", {}) == DEFAULT_CAPACITY

@pytest.mark.parametrize("kind", ["bank", "employer"])
def test_population_tag_is_ignored_for_other_kinds(kind):
    assert estimate_capacity(kind, {"population": "1200"}) == DEFAULT_CAPACITY

def test_capacity_is_always_positive():
    # схема БД требует capacity > 0
    for tags in ({}, {"population": "0"}, {"population": "-1"}, {"population": "abc"}):
        assert estimate_capacity("settlement", tags) > 0

#  build_subjects (без БД)
def test_empty_rows_give_no_subjects():
    assert build_subjects([]) == []

def test_object_in_two_domains_becomes_one_subject_with_two_capacities():
    rows = [
        row(domain="labor", role="supply"),
        row(domain="money", role="demand"),
    ]
    subjects = build_subjects(rows)
    
    assert len(subjects) == 1
    assert subjects[0].capacities == [
        Capacity("labor", "supply", DEFAULT_CAPACITY),
        Capacity("money", "demand", DEFAULT_CAPACITY),
    ]

def test_each_object_becomes_its_own_subject_in_input_order():
    rows = [row(osm_id=1), row(osm_id=2), row(osm_type="way", osm_id=1)]
    subjects = build_subjects(rows)

    assert [s.id for s in subjects] == ["s_n1", "s_n2", "s_w1"]

def test_subject_fields_come_from_the_first_row():
    tags = {"name": "Посёлок", "addr:street": "Лесная", "addr:housenumber": "5", "population": "300"}
    subject = build_subjects([row(tags=tags, lon=39.1, lat=57.2, district_id="d1")])[0]

    assert (subject.name, subject.address, subject.kind) == ("Посёлок", "Лесная, 5", "settlement")
    assert (subject.lon, subject.lat, subject.district_id) == (39.1, 57.2, "d1")
    assert subject.capacities[0].capacity == 300.0

def test_missing_name_and_district_stay_none():
    subject = build_subjects([row(tags={})])[0]

    assert subject.name is None
    assert subject.district_id is None

def test_repeated_rows_for_overlapping_districts_do_not_duplicate_capacities():
    # точка в двух районах: SQL отдаёт строку на каждую пару (домен, район)
    rows = [
        row(domain="labor", role="supply", district_id="d1"),
        row(domain="labor", role="supply", district_id="d2"),
        row(domain="money", role="demand", district_id="d1"),
        row(domain="money", role="demand", district_id="d2"),
    ]
    subject = build_subjects(rows)[0]

    assert [c.domain for c in subject.capacities] == ["labor", "money"]
    assert subject.district_id == "d1"  # берётся первый район

SQUARE_1 = {"type": "Polygon", "coordinates": [[[39.8, 57.5], [40.0, 57.5], [40.0, 57.7],
                                                 [39.8, 57.7], [39.8, 57.5]]]}
SQUARE_2 = {"type": "Polygon", "coordinates": [[[39.85, 57.55], [40.05, 57.55], [40.05, 57.75],
                                                 [39.85, 57.75], [39.85, 57.55]]]}
FAR_POINT = {"type": "Point", "coordinates": [41.5, 58.5]}
POINT = {"type": "Point", "coordinates": [39.9, 57.6]}

def add_object(con, osm_type, osm_id, tags, geometry, region="yaroslavl"):
    con.execute(
        "INSERT INTO osm_objects (osm_type, osm_id, tags, geom, region) "
        "VALUES (?, ?, CAST(? AS JSON), ST_GeomFromGeoJSON(?), ?)",
        [osm_type, osm_id, json.dumps(tags), json.dumps(geometry), region],
    )

def classify(con, osm_type, osm_id, domain, role, kind):
    con.execute(
        "INSERT INTO osm_classification (osm_type, osm_id, domain, role, kind) "
        "VALUES (?, ?, ?, ?, ?)",
        [osm_type, osm_id, domain, role, kind],
    )

def add_settlement(con, osm_id=1, geometry=POINT, region="yaroslavl", tags=None):
    add_object(con, "node", osm_id, tags or {"name": "Посёлок", "population": "500"}, geometry, region)
    classify(con, "node", osm_id, "money", "demand", "settlement")
    classify(con, "node", osm_id, "labor", "supply", "settlement")

def test_fetch_rows_returns_one_row_per_object_and_domain(con):
    add_settlement(con)
    rows = fetch_rows(con, "yaroslavl", DOMAINS)

    assert sorted(r[5] for r in rows) == ["labor", "money"]
    assert {(r[0], r[1]) for r in rows} == {("node", 1)}

def test_fetch_rows_skips_disabled_domains(con):
    add_settlement(con)
    classify(con, "node", 1, "goods", "supply", "settlement")
    rows = fetch_rows(con, "yaroslavl", DOMAINS)

    assert "goods" not in {r[5] for r in rows}

def test_fetch_rows_skips_unclassified_objects(con):
    add_object(con, "node", 9, {"building": "yes"}, POINT)  # без записей в osm_classification

    assert fetch_rows(con, "yaroslavl", DOMAINS) == []

def test_fetch_rows_filters_by_region(con):
    add_settlement(con, osm_id=1, region="yaroslavl")
    add_settlement(con, osm_id=2, region="other")
    rows = fetch_rows(con, "yaroslavl", DOMAINS)

    assert {r[1] for r in rows} == {1}

def test_fetch_rows_uses_centroid_for_polygons(con):
    add_settlement(con, geometry={"type": "Polygon", "coordinates": [[[39.0, 57.0], [40.0, 57.0],
                                                                      [40.0, 58.0], [39.0, 58.0],
                                                                      [39.0, 57.0]]]})
    lon, lat = fetch_rows(con, "yaroslavl", DOMAINS)[0][3:5]

    assert (lon, lat) == pytest.approx((39.5, 57.5))

def test_fetch_rows_finds_district_of_point(con):
    Repository(con).save_districts([District("d1", "Первый", SQUARE_1)])
    add_settlement(con)
    rows = fetch_rows(con, "yaroslavl", DOMAINS)

    assert {r[8] for r in rows} == {"d1"}

def test_fetch_rows_gives_null_district_outside_all_districts(con):
    Repository(con).save_districts([District("d1", "Первый", SQUARE_1)])
    add_settlement(con, geometry=FAR_POINT)
    rows = fetch_rows(con, "yaroslavl", DOMAINS)

    assert {r[8] for r in rows} == {None}

def test_fetch_rows_works_without_districts(con):
    add_settlement(con)
    rows = fetch_rows(con, "yaroslavl", DOMAINS)

    assert len(rows) == 2
    assert {r[8] for r in rows} == {None}

# вся цепочка: БД -> субъекты -> БД 
def test_full_chain_saves_subjects_with_capacities_and_district(con):
    repo = Repository(con)
    repo.save_districts([District("d1", "Первый", SQUARE_1)])
    add_settlement(con, osm_id=1, tags={"name": "Посёлок", "population": "500"})
    add_object(con, "node", 2, {"amenity": "bank", "name": "Банк"}, {"type": "Point", "coordinates": [39.95, 57.65]})
    classify(con, "node", 2, "money", "supply", "bank")
    repo.save_subjects(build_subjects(fetch_rows(con, "yaroslavl", DOMAINS)))
    saved = {s.id: s for s in repo.get_subjects()}
    
    assert set(saved) == {"s_n1", "s_n2"}
    assert saved["s_n1"].district_id == "d1"
    assert [(c.domain, c.role, c.capacity) for c in saved["s_n1"].capacities] == [
        ("labor", "supply", 500.0), ("money", "demand", 500.0)]
    assert saved["s_n2"].kind == "bank"
    assert saved["s_n2"].capacities == [Capacity("money", "supply", DEFAULT_CAPACITY)]

def test_overlapping_districts_do_not_break_saving(con):
    # точка (39.9, 57.6) лежит в обоих квадратах: без защиты от дублей запись упала бы на PRIMARY KEY
    repo = Repository(con)
    repo.save_districts([District("d2", "Второй", SQUARE_2), District("d1", "Первый", SQUARE_1)])
    add_settlement(con)
    repo.save_subjects(build_subjects(fetch_rows(con, "yaroslavl", DOMAINS)))
    subject = repo.get_subjects()[0]
    
    assert subject.district_id == "d1"
    assert len(subject.capacities) == 2

def test_rerun_gives_same_ids_and_replaces_data(con):
    repo = Repository(con)
    add_settlement(con)
    for _ in range(2):
        repo.save_subjects(build_subjects(fetch_rows(con, "yaroslavl", DOMAINS)))

    assert [s.id for s in repo.get_subjects()] == ["s_n1"]