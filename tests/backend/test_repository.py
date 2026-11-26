import duckdb
import pytest
from backend.economy.models import Capacity, District, Edge, Metric, Subject

def make_subject(subject_id, *capacities, district_id="d1", name=None, group="finance"):
    return Subject(
        id=subject_id, name=name, kind="bank", group=group, lon=39.9, lat=57.6,
        address=None, district_id=district_id, capacities=list(capacities))

def make_edge(edge_id, domain="money", from_id="s1", to_id="s2", weight=0.5):
    return Edge(edge_id, domain, from_id, to_id, distance_km=1.5, weight=weight)

# subjects и capacities
def test_subjects_roundtrip(repo):
    # репозиторий отдаёт ёмкости субъекта отсортированными по домену (labor < money)
    subjects = [
        make_subject("s1", Capacity("labor", "demand", 3.0), Capacity("money", "supply", 10.0),
                     name="Банк"),
        make_subject("s2", Capacity("money", "demand", 5.0), district_id=None),
    ]
    repo.save_subjects(subjects)
    assert repo.get_subjects() == subjects

def test_subject_without_capacities_is_kept_without_filter(repo):
    repo.save_subjects([make_subject("s1")])
    result = repo.get_subjects()

    assert [s.id for s in result] == ["s1"]
    assert result[0].capacities == []

def test_get_subjects_filters_domains_and_capacities(repo):
    repo.save_subjects([
        make_subject("s1", Capacity("money", "supply", 10.0), Capacity("labor", "demand", 3.0)),
        make_subject("s2", Capacity("labor", "supply", 4.0)),
        make_subject("s3"),
    ])
    result = repo.get_subjects(["money"])

    # остаются только субъекты с ёмкостью в домене, и только эта ёмкость
    assert [s.id for s in result] == ["s1"]
    assert result[0].capacities == [Capacity("money", "supply", 10.0)]

def test_get_subjects_with_empty_domain_list_returns_nothing(repo):
    repo.save_subjects([make_subject("s1", Capacity("money", "supply", 10.0))])
    
    assert repo.get_subjects([]) == []

def test_save_subjects_replaces_previous_data(repo):
    repo.save_subjects([make_subject("s1", Capacity("money", "supply", 10.0))])
    repo.save_subjects([make_subject("s2", Capacity("labor", "demand", 2.0))])

    assert [s.id for s in repo.get_subjects()] == ["s2"]

def test_save_subjects_rejects_non_positive_capacity(repo):
    with pytest.raises(duckdb.ConstraintException):
        repo.save_subjects([make_subject("s1", Capacity("money", "supply", 0.0))])

def test_failed_save_subjects_keeps_old_data(repo):
    old = [make_subject("s1", Capacity("money", "supply", 10.0))]
    repo.save_subjects(old)
    with pytest.raises(duckdb.ConstraintException):
        repo.save_subjects([make_subject("s2", Capacity("money", "supply", -1.0))])

    assert repo.get_subjects() == old

# edges 
def test_edges_roundtrip(repo):
    edges = [make_edge("e1"), make_edge("e2", domain="labor", weight=1.0)]
    repo.save_edges(edges)

    assert repo.get_edges() == edges

def test_get_edges_filters_by_domain(repo):
    repo.save_edges([make_edge("e1", "money"), make_edge("e2", "labor")])

    assert [e.id for e in repo.get_edges(["labor"])] == ["e2"]
    assert repo.get_edges([]) == []

def test_save_edges_replaces_previous_edges(repo):
    repo.save_edges([make_edge("e1")])
    repo.save_edges([make_edge("e2")])

    assert [e.id for e in repo.get_edges()] == ["e2"]

def test_insert_edges_appends(repo):
    repo.save_edges([make_edge("e1")])
    repo.insert_edges([make_edge("e2", "labor")])

    assert [e.id for e in repo.get_edges()] == ["e1", "e2"]

def test_delete_edges_by_domain_keeps_other_domains(repo):
    repo.save_edges([make_edge("e1", "money"), make_edge("e2", "labor")])
    repo.delete_edges_by_domain("money")

    assert [e.id for e in repo.get_edges()] == ["e2"]

@pytest.mark.parametrize("weight", [0.0, -0.1, 1.5])
def test_edge_weight_must_be_in_unit_interval(repo, weight):
    with pytest.raises(duckdb.ConstraintException):
        repo.save_edges([make_edge("e1", weight=weight)])

def test_failed_save_edges_keeps_old_edges(repo):
    repo.save_edges([make_edge("e1")])
    with pytest.raises(duckdb.ConstraintException):
        repo.save_edges([make_edge("e2"), make_edge("e3", weight=2.0)])

    assert [e.id for e in repo.get_edges()] == ["e1"]

def test_duplicate_edge_id_is_rejected(repo):
    with pytest.raises(duckdb.ConstraintException):
        repo.save_edges([make_edge("e1"), make_edge("e1")])

# транзакции 
def test_transaction_commits_all_operations(repo):
    with repo.transaction():
        repo.save_subjects([make_subject("s1", Capacity("money", "supply", 10.0))])
        repo.save_edges([make_edge("e1")])

    assert [s.id for s in repo.get_subjects()] == ["s1"]
    assert [e.id for e in repo.get_edges()] == ["e1"]

def test_transaction_rolls_back_all_operations_on_error(repo):
    old_subjects = [make_subject("old", Capacity("money", "supply", 1.0))]
    repo.save_subjects(old_subjects)
    with pytest.raises(duckdb.ConstraintException):
        with repo.transaction():
            repo.save_subjects([make_subject("s1", Capacity("money", "supply", 10.0))])
            repo.save_edges([make_edge("e1", weight=5.0)])  # нарушает CHECK

    # откатилась и запись субъектов, выполненная до ошибки
    assert repo.get_subjects() == old_subjects
    assert repo.get_edges() == []

def test_repository_is_usable_after_rollback(repo):
    with pytest.raises(duckdb.ConstraintException):
        repo.save_edges([make_edge("e1", weight=5.0)])
    repo.save_edges([make_edge("e2")])  # транзакция не осталась «зависшей»

    assert [e.id for e in repo.get_edges()] == ["e2"]

# metrics
def test_metrics_roundtrip_and_order(repo):
    metrics = [
        Metric("district", "d1", "money", 4, 3, 1.5, True),
        Metric("region", None, "money", 10, 8, 1.6, False),
        Metric("district", "d1", "all", 6, 5, 1.0, False),
    ]
    repo.save_metrics(metrics)
    result = repo.get_metrics()

    # сначала регион, потом районы; внутри района по домену
    assert [(m.scope, m.district_id, m.domain) for m in result] == [
        ("region", None, "money"),
        ("district", "d1", "all"),
        ("district", "d1", "money"),
    ]
    assert result[0] == metrics[1]

def test_save_metrics_replaces_previous_rows(repo):
    repo.save_metrics([Metric("region", None, "money", 1, 0, 0.0, True)])
    repo.save_metrics([Metric("region", None, "labor", 2, 1, 1.0, True)])
    
    assert [m.domain for m in repo.get_metrics()] == ["labor"]

def test_metric_scope_is_checked_by_schema(repo):
    with pytest.raises(duckdb.ConstraintException):
        repo.save_metrics([Metric("city", None, "money", 1, 0, 0.0, True)])

# districts
SQUARE = {
    "type": "Polygon",
    "coordinates": [[[39.8, 57.5], [40.0, 57.5], [40.0, 57.7], [39.8, 57.7], [39.8, 57.5]]],
}

def test_districts_roundtrip(repo):
    repo.save_districts([District("d2", "Второй", SQUARE), District("d1", "Первый", SQUARE)])
    result = repo.get_districts()

    assert [d.id for d in result] == ["d1", "d2"]  # сортировка по id
    assert result[0].name == "Первый"
    assert result[0].geom["type"] == "Polygon"
    assert len(result[0].geom["coordinates"][0]) == 5

def test_save_districts_replaces_previous_data(repo):
    repo.save_districts([District("d1", "Первый", SQUARE)])
    repo.save_districts([District("d2", "Второй", SQUARE)])

    assert [d.id for d in repo.get_districts()] == ["d2"]

def test_district_without_geom_raises(repo):
    repo._con.execute("INSERT INTO districts (id, name, geom) VALUES ('d1', 'Первый', NULL)")

    with pytest.raises(ValueError, match="d1"):
        repo.get_districts()