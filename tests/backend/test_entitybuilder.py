# Тесты сборщика сущностей
import json
import pytest

from backend.economy.models import Capacity, District
from backend.economy.repository import Repository
from backend.entity_builder.__main__ import (
    DEFAULT_CAPACITY,
    DEFAULT_LEVELS,
    METERS_PER_DEGREE,
    build_subjects,
    fetch_rows,
    footprint_area_m2,
    make_address,
    make_subject_id,
    parse_levels,
    residence_capacity,
)

DOMAINS = ["money", "labor"]


def square(lon, lat, size):
    # квадрат со стороной size градусов, левый нижний угол в (lon, lat)
    return {"type": "Polygon", "coordinates": [[[lon, lat], [lon + size, lat], [lon + size, lat + size],
                                                 [lon, lat + size], [lon, lat]]]}

# квадрат 0.001° на экваторе: сторона ~111.2 м, площадь ~12365 м²
HOUSE = square(0.0, 0.0, 0.001)
HOUSE_AREA = (METERS_PER_DEGREE * 0.001) ** 2


def row(osm_type="node", osm_id=1, tags=None, lon=39.9, lat=57.6, domain="money", role="supply",
        kind="bank", district_id=None, geometry=None):
    # одна строка так, как её отдаёт fetch_rows: объект OSM в одном домене
    return (osm_type, osm_id, json.dumps(tags or {}), lon, lat, domain, role, kind, district_id,
            json.dumps(geometry) if geometry else None)

def house_rows(osm_id, tags=None, geometry=HOUSE, **kwargs):
    # жилой дом участвует в двух доменах: money (спрос) и labor (предложение)
    return [
        row(osm_id=osm_id, tags=tags, domain="labor", role="supply", kind="residence", geometry=geometry, **kwargs),
        row(osm_id=osm_id, tags=tags, domain="money", role="demand", kind="residence", geometry=geometry, **kwargs),
    ]


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

#  footprint_area_m2
def test_area_of_small_square_at_equator():
    assert footprint_area_m2(HOUSE) == pytest.approx(HOUSE_AREA, rel=1e-3)

def test_area_shrinks_with_latitude():
    # на широте 60° градус долготы вдвое короче, поэтому площадь вдвое меньше
    assert footprint_area_m2(square(0.0, 60.0, 0.001)) == pytest.approx(HOUSE_AREA / 2, rel=1e-2)

def test_area_of_multipolygon_is_sum_of_parts():
    multi = {"type": "MultiPolygon", "coordinates": [HOUSE["coordinates"], square(0.01, 0.0, 0.001)["coordinates"]]}

    assert footprint_area_m2(multi) == pytest.approx(2 * HOUSE_AREA, rel=1e-3)

@pytest.mark.parametrize("geometry", [
    None,
    {"type": "Point", "coordinates": [39.9, 57.6]},
    {"type": "LineString", "coordinates": [[39.9, 57.6], [39.91, 57.61]]},
])

def test_area_is_zero_without_polygon(geometry):
    assert footprint_area_m2(geometry) == 0.0

#  parse_levels
@pytest.mark.parametrize("value, expected", [
    ("5", 5.0),
    ("2,5", 2.5),
    ("2.5", 2.5),
    ("5;6", 5.0),  # берём первое число
    (" 9 ", 9.0),
])

def test_levels_from_tag(value, expected):
    assert parse_levels({"building:levels": value}) == expected

@pytest.mark.parametrize("tags", [{}, {"building:levels": "много"}, {"building:levels": ""}, {"building:levels": "0"}])
def test_levels_default_when_tag_is_missing_or_bad(tags):
    assert parse_levels(tags) == DEFAULT_LEVELS

#  residence_capacity
def test_residence_capacity_is_area_times_levels():
    capacity = residence_capacity({"building:levels": "3"}, HOUSE)

    assert capacity == pytest.approx(3 * HOUSE_AREA, rel=1e-3)

def test_residence_without_levels_counts_as_one_level():
    assert residence_capacity({}, HOUSE) == pytest.approx(HOUSE_AREA, rel=1e-3)

def test_residence_capacity_is_none_without_area():
    assert residence_capacity({"building:levels": "3"}, {"type": "Point", "coordinates": [0, 0]}) is None
    assert residence_capacity({}, None) is None

#  build_subjects (без БД)
def test_empty_rows_give_no_subjects():
    assert build_subjects([]) == []

def test_residence_in_two_domains_gets_one_capacity_value_in_both():
    subjects = build_subjects(house_rows(1, tags={"building:levels": "2"}))

    assert len(subjects) == 1
    capacity = 2 * HOUSE_AREA
    assert subjects[0].capacities == [
        Capacity("labor", "supply", pytest.approx(capacity, rel=1e-3)),
        Capacity("money", "demand", pytest.approx(capacity, rel=1e-3)),
    ]

def test_settlement_is_a_subject_without_capacities():
    # справочный объект: на карте есть, в графе не участвует; population остаётся в osm_objects.tags
    rows = [
        row(kind="settlement", domain="labor", role="supply", tags={"name": "Посёлок", "population": "300"}),
        row(kind="settlement", domain="money", role="demand", tags={"name": "Посёлок", "population": "300"}),
    ]
    subjects = build_subjects(rows)

    assert [(s.id, s.kind, s.name) for s in subjects] == [("s_n1", "settlement", "Посёлок")]
    assert subjects[0].capacities == []

def test_bank_and_employer_get_average_capacity_of_residences():
    # два дома: один этаж и три этажа, среднее = 2 * площадь
    rows = (
        house_rows(1)
        + house_rows(2, tags={"building:levels": "3"})
        + [row(osm_id=3, kind="bank", domain="money", role="supply"),
           row(osm_id=4, kind="employer", domain="labor", role="demand")]
    )
    saved = {s.id: s for s in build_subjects(rows)}

    average = pytest.approx(2 * HOUSE_AREA, rel=1e-3)
    assert saved["s_n3"].capacities == [Capacity("money", "supply", average)]
    assert saved["s_n4"].capacities == [Capacity("labor", "demand", average)]

def test_residence_without_area_gets_average_of_the_rest():
    rows = house_rows(1) + house_rows(2, geometry=None)
    saved = {s.id: s for s in build_subjects(rows)}

    assert [c.capacity for c in saved["s_n2"].capacities] == [pytest.approx(HOUSE_AREA, rel=1e-3)] * 2

def test_average_ignores_residences_without_area():
    # дом без размеров не должен тянуть среднее вниз до нуля
    rows = house_rows(1) + house_rows(2, geometry=None) + [row(osm_id=3)]
    saved = {s.id: s for s in build_subjects(rows)}

    assert saved["s_n3"].capacities[0].capacity == pytest.approx(HOUSE_AREA, rel=1e-3)

def test_default_capacity_when_there_are_no_residences():
    subject = build_subjects([row(kind="bank")])[0]

    assert subject.capacities == [Capacity("money", "supply", DEFAULT_CAPACITY)]

def test_capacity_is_always_positive():
    # схема БД требует capacity > 0
    rows = house_rows(1, geometry=None) + [row(osm_id=2)]

    assert all(c.capacity > 0 for s in build_subjects(rows) for c in s.capacities)

def test_each_object_becomes_its_own_subject_in_input_order():
    rows = [row(osm_id=1), row(osm_id=2), row(osm_type="way", osm_id=1)]
    subjects = build_subjects(rows)

    assert [s.id for s in subjects] == ["s_n1", "s_n2", "s_w1"]

def test_subject_fields_come_from_the_first_row():
    tags = {"name": "Банк", "addr:street": "Лесная", "addr:housenumber": "5"}
    subject = build_subjects([row(tags=tags, lon=39.1, lat=57.2, district_id="d1")])[0]

    assert (subject.name, subject.address, subject.kind) == ("Банк", "Лесная, 5", "bank")
    assert (subject.lon, subject.lat, subject.district_id) == (39.1, 57.2, "d1")

def test_missing_name_and_district_stay_none():
    subject = build_subjects([row(tags={})])[0]

    assert subject.name is None
    assert subject.district_id is None

def test_repeated_rows_for_overlapping_districts_do_not_duplicate_capacities():
    # точка в двух районах: SQL отдаёт строку на каждую пару (домен, район)
    rows = [
        row(domain="labor", role="demand", district_id="d1"),
        row(domain="labor", role="demand", district_id="d2"),
        row(domain="money", role="supply", district_id="d1"),
        row(domain="money", role="supply", district_id="d2"),
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
# дом в районе SQUARE_1: сторона 0.001°, на широте 57.6 площадь ~6600 м²
HOUSE_IN_DISTRICT = square(39.9, 57.6, 0.001)

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

def add_residence(con, osm_id=10, geometry=HOUSE_IN_DISTRICT, tags=None):
    add_object(con, "way", osm_id, tags or {"building": "apartments", "building:levels": "5"}, geometry)
    classify(con, "way", osm_id, "money", "demand", "residence")
    classify(con, "way", osm_id, "labor", "supply", "residence")

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

def test_fetch_rows_gives_geometry_only_for_residences(con):
    add_settlement(con)
    add_residence(con)
    geometry_by_kind = {r[7]: r[9] for r in fetch_rows(con, "yaroslavl", DOMAINS)}

    assert geometry_by_kind["settlement"] is None
    assert json.loads(geometry_by_kind["residence"])["type"] == "Polygon"

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
    add_settlement(con, osm_id=1)
    add_residence(con, osm_id=10)
    add_object(con, "node", 2, {"amenity": "bank", "name": "Банк"}, {"type": "Point", "coordinates": [39.95, 57.65]})
    classify(con, "node", 2, "money", "supply", "bank")
    repo.save_subjects(build_subjects(fetch_rows(con, "yaroslavl", DOMAINS)))
    saved = {s.id: s for s in repo.get_subjects()}

    assert set(saved) == {"s_n1", "s_n2", "s_w10"}
    assert saved["s_n1"].district_id == "d1"
    assert saved["s_n1"].capacities == []  # населённый пункт без ёмкостей
    house_capacity = footprint_area_m2(HOUSE_IN_DISTRICT) * 5
    assert [(c.domain, c.role) for c in saved["s_w10"].capacities] == [("labor", "supply"), ("money", "demand")]
    assert saved["s_w10"].capacities[0].capacity == pytest.approx(house_capacity)
    assert saved["s_n2"].kind == "bank"
    assert saved["s_n2"].capacities == [Capacity("money", "supply", pytest.approx(house_capacity))]  # среднее по домам

def test_overlapping_districts_do_not_break_saving(con):
    # точка (39.9, 57.6) лежит в обоих квадратах: без защиты от дублей запись упала бы на PRIMARY KEY
    repo = Repository(con)
    repo.save_districts([District("d2", "Второй", SQUARE_2), District("d1", "Первый", SQUARE_1)])
    add_residence(con, geometry=square(39.9, 57.6, 0.001))
    repo.save_subjects(build_subjects(fetch_rows(con, "yaroslavl", DOMAINS)))
    subject = repo.get_subjects()[0]

    assert subject.district_id == "d1"
    assert len(subject.capacities) == 2

def test_rerun_gives_same_ids_and_replaces_data(con):
    repo = Repository(con)
    add_residence(con)
    for _ in range(2):
        repo.save_subjects(build_subjects(fetch_rows(con, "yaroslavl", DOMAINS)))

    assert [s.id for s in repo.get_subjects()] == ["s_w10"]