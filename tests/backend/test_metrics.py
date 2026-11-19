import pytest
from backend.economy.models import Capacity, Edge, Subject
from backend.metrics.calculator import ALL, compute_metrics

DOMAINS = ["money", "labor"]

def make_subject(subject_id, district_id, *domains):
    return Subject(
        id=subject_id, name=None, kind="bank", lon=39.9, lat=57.6, address=None,
        district_id=district_id,
        capacities=[Capacity(domain, "supply", 1.0) for domain in domains])

def make_edge(edge_id, domain, from_id, to_id):
    return Edge(edge_id, domain, from_id, to_id, distance_km=1.0, weight=0.5)

def compute(subjects, edges, district_ids=("d1", "d2"), domains=DOMAINS, threshold=3):
    return compute_metrics(subjects, edges, list(district_ids), domains, threshold)

def find(rows, scope, district_id, domain):
    # ровно одна строка для выбранной области и домена
    found = [r for r in rows if (r.scope, r.district_id, r.domain) == (scope, district_id, domain)]
    assert len(found) == 1, f"ожидалась одна строка, найдено {len(found)}"
    return found[0]

@pytest.fixture
def small_graph():
    subjects = [
        make_subject("s1", "d1", "money", "labor"),
        make_subject("s2", "d1", "money"),
        make_subject("s3", "d2", "money"),
        make_subject("s4", "d2", "labor"),
    ]
    edges = [
        make_edge("e1", "money", "s1", "s2"),
        make_edge("e2", "money", "s2", "s3"),
        make_edge("e3", "labor", "s1", "s4"),
    ]
    return subjects, edges

# структура результата
def test_rows_cover_every_scope_and_domain_once(small_graph):
    rows = compute(*small_graph)

    # (регион + 2 района) * (2 домена + all)
    assert len(rows) == 3 * 3
    keys = {(r.scope, r.district_id, r.domain) for r in rows}
    assert len(keys) == len(rows)
    assert {r.domain for r in rows} == {"money", "labor", ALL}

def test_region_rows_come_first(small_graph):
    rows = compute(*small_graph)

    assert [r.scope for r in rows[:3]] == ["region"] * 3
    assert all(r.scope == "district" for r in rows[3:])


# region
def test_region_counts_per_domain(small_graph):
    rows = compute(*small_graph)
    money = find(rows, "region", None, "money")
    assert (money.node_count, money.edge_count) == (3, 2)
    labor = find(rows, "region", None, "labor")
    assert (labor.node_count, labor.edge_count) == (2, 1)

def test_all_domain_counts_subject_once_and_sums_edges(small_graph):
    rows = compute(*small_graph)
    total = find(rows, "region", None, ALL)

    # s1 участвует в двух доменах, но как субъект считается один раз
    assert total.node_count == 4
    assert total.edge_count == 3

def test_avg_degree_is_twice_edges_over_nodes(small_graph):
    rows = compute(*small_graph)
    money = find(rows, "region", None, "money")

    # степени цепочки s1 - s2 - s3: 1, 2, 1
    assert money.avg_degree == pytest.approx(4 / 3)

# district 
def test_district_counts_nodes_of_that_district_only(small_graph):
    rows = compute(*small_graph)
    d1 = find(rows, "district", "d1", "money")
    d2 = find(rows, "district", "d2", "money")

    assert (d1.node_count, d2.node_count) == (2, 1)

def test_edge_belongs_to_district_if_any_end_lies_in_it(small_graph):
    rows = compute(*small_graph)
    
    # e1 целиком в d1, e2 соединяет d1 и d2 и считается в обоих районах
    assert find(rows, "district", "d1", "money").edge_count == 2
    assert find(rows, "district", "d2", "money").edge_count == 1

def test_district_avg_degree_uses_degrees_from_whole_graph(small_graph):
    rows = compute(*small_graph)
    d1 = find(rows, "district", "d1", "money")

    # у s1 степень 1, у s2 степень 2 (ребро в d2 тоже учитывается)
    assert d1.avg_degree == pytest.approx(1.5)

def test_subject_without_district_is_counted_only_in_region():
    subjects = [make_subject("s1", None, "money"), make_subject("s2", "d1", "money")]
    rows = compute(subjects, [], district_ids=["d1"])

    assert find(rows, "region", None, "money").node_count == 2
    assert find(rows, "district", "d1", "money").node_count == 1

# low_data 
@pytest.mark.parametrize("node_count, expected", [(2, True), (3, False), (4, False)])
def test_low_data_threshold_is_strict(node_count, expected):
    subjects = [make_subject(f"s{i}", "d1", "money") for i in range(node_count)]
    rows = compute(subjects, [], district_ids=["d1"], threshold=3)

    assert find(rows, "region", None, "money").low_data is expected

# пустые данные
def test_empty_input_gives_zero_rows_without_division_error():
    rows = compute([], [], district_ids=["d1"])

    assert len(rows) == 2 * 3
    for row in rows:
        assert (row.node_count, row.edge_count, row.avg_degree) == (0, 0, 0.0)
        assert row.low_data is True

def test_district_without_subjects_gets_zero_row(small_graph):
    rows = compute(*small_graph, district_ids=["d1", "empty"])
    empty = find(rows, "district", "empty", "money")
    
    assert (empty.node_count, empty.edge_count, empty.avg_degree) == (0, 0, 0.0)
    assert empty.low_data is True

def test_no_districts_gives_region_rows_only(small_graph):
    rows = compute(*small_graph, district_ids=[])

    assert {r.scope for r in rows} == {"region"}

# домены и целостность данных
def test_capacity_in_disabled_domain_is_ignored():
    subjects = [make_subject("s1", "d1", "money", "goods")]
    rows = compute(subjects, [])

    assert {r.domain for r in rows} == {"money", "labor", ALL}
    assert find(rows, "region", None, "money").node_count == 1
    assert find(rows, "region", None, "labor").node_count == 0

def test_edge_to_unknown_subject_raises():
    subjects = [make_subject("s1", "d1", "money")]
    edges = [make_edge("e1", "money", "s1", "ghost")]
    with pytest.raises(ValueError, match="ghost"):
        compute(subjects, edges)

def test_edge_to_subject_from_another_domain_raises():
    # s2 участвует только в labor, значит ребро money к нему некорректно
    subjects = [make_subject("s1", "d1", "money"), make_subject("s2", "d1", "labor")]
    edges = [make_edge("e1", "money", "s1", "s2")]
    with pytest.raises(ValueError, match="e1|s2"):
        compute(subjects, edges)

def test_input_is_not_modified(small_graph):
    subjects, edges = small_graph
    subjects_before = [(s.id, s.district_id, list(s.capacities)) for s in subjects]
    edges_before = list(edges)
    compute(subjects, edges)

    assert [(s.id, s.district_id, list(s.capacities)) for s in subjects] == subjects_before
    assert edges == edges_before

# связка с БД 
def test_metrics_from_database_ignore_disabled_domains(repo):
    # субъект goods-домена и его ребро в БД есть, но домен отключён
    repo.save_subjects([
        make_subject("s1", "d1", "money"),
        make_subject("s2", "d1", "money"),
        make_subject("g1", "d1", "goods"),
        make_subject("g2", "d1", "goods"),
    ])
    repo.save_edges([
        make_edge("e1", "money", "s1", "s2"),
        make_edge("e2", "goods", "g1", "g2"),
    ])
    rows = compute_metrics(
        repo.get_subjects(["money"]), repo.get_edges(["money"]),
        district_ids=["d1"], domains=["money"], low_data_threshold=1)
    total = find(rows, "region", None, ALL)
    
    assert (total.node_count, total.edge_count) == (2, 1)
    assert {r.domain for r in rows} == {"money", ALL}

def test_metrics_roundtrip_through_database(repo, small_graph):
    rows = compute(*small_graph)
    repo.save_metrics(rows)
    saved = repo.get_metrics()
    
    assert len(saved) == len(rows)
    assert {(m.scope, m.district_id, m.domain, m.node_count, m.edge_count) for m in saved} == {
        (m.scope, m.district_id, m.domain, m.node_count, m.edge_count) for m in rows}