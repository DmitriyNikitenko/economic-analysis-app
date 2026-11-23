import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch
import pytest
import numpy as np

from backend.economy.models import Capacity, Edge, Subject
from backend.graph import __main__ as graph_main
from backend.graph.engine import MIN_VISIBLE_DISTANCE, build_gravity_edges, distance
from backend.graph.updater import update_edges
from backend.graph.equilibrium import build_equilibrium_edges, solve_flows

def make_config(
    radius_km: float = 100.0,
    beta: float = 2.0,
    enabled_domains: list[str] | None = None,
    extra_domains: dict[str, tuple[float, float]] | None = None,
):
    domains = {"labor": SimpleNamespace(radius_km=radius_km, beta=beta)}
    if extra_domains:
        for dom, (r, b) in extra_domains.items():
            domains[dom] = SimpleNamespace(radius_km=r, beta=b)
    return SimpleNamespace(
        enabled_domains=enabled_domains if enabled_domains is not None else ["labor"],
        domains=domains,
    )


# engine.py

def test_build_gravity_edges_empty_inputs():
    cfg = make_config()
    assert build_gravity_edges([], cfg) == []


def test_build_gravity_edges_only_demand_or_only_supply():
    cfg = make_config()
    only_demand = [Subject("d1", "D", "org", 0.0, 0.0, None, None, [Capacity("labor", "demand", 10.0)])]
    only_supply = [Subject("s1", "S", "org", 0.0, 0.0, None, None, [Capacity("labor", "supply", 10.0)])]

    assert build_gravity_edges(only_demand, cfg) == []
    assert build_gravity_edges(only_supply, cfg) == []


def test_build_gravity_edges_single_pair_attributes():
    cfg = make_config(radius_km=200.0, beta=2.0)
    subjects = [
        Subject("d1", "Спрос", "org", 30.0, 60.0, None, "dist1", [Capacity("labor", "demand", 10.0)]),
        Subject("s1", "Предложение", "org", 30.0, 60.1, None, "dist1", [Capacity("labor", "supply", 50.0)]),
    ]

    edges = build_gravity_edges(subjects, cfg)

    assert len(edges) == 1
    e = edges[0]
    assert uuid.UUID(e.id).version == 4
    assert e.domain == "labor"
    assert e.from_id == "d1"
    assert e.to_id == "s1"
    assert e.weight == pytest.approx(1.0)
    assert e.distance_km == round(distance(30.0, 60.0, 30.0, 60.1), 3)


def test_build_gravity_edges_weights_sum_to_one():
    cfg = make_config(radius_km=200.0, beta=2.0)
    subjects = [
        Subject("d1", "Спрос", "org", 0.0, 0.0, None, "dist1", [Capacity("labor", "demand", 10.0)]),
        Subject("s1", "Ближний", "org", 0.0, 0.1, None, "dist1", [Capacity("labor", "supply", 100.0)]),
        Subject("s2", "Дальний", "org", 0.0, 0.2, None, "dist1", [Capacity("labor", "supply", 100.0)]),
    ]

    edges = build_gravity_edges(subjects, cfg)

    assert len(edges) == 2
    assert sum(e.weight for e in edges) == pytest.approx(1.0)
    by_to = {e.to_id: e.weight for e in edges}
    assert by_to["s1"] > by_to["s2"]


def test_build_gravity_edges_exact_formula():
    beta = 1.5
    cfg = make_config(radius_km=200.0, beta=beta)
    subjects = [
        Subject("d1", "Спрос", "org", 0.0, 0.0, None, None, [Capacity("labor", "demand", 10.0)]),
        Subject("s1", "П1", "org", 0.0, 0.1, None, None, [Capacity("labor", "supply", 100.0)]),
        Subject("s2", "П2", "org", 0.0, 0.3, None, None, [Capacity("labor", "supply", 250.0)]),
    ]

    edges = build_gravity_edges(subjects, cfg)
    by_to = {e.to_id: e for e in edges}

    d1 = distance(0.0, 0.0, 0.0, 0.1)
    d2 = distance(0.0, 0.0, 0.0, 0.3)
    w1 = 100.0 * (d1 ** -beta)
    w2 = 250.0 * (d2 ** -beta)

    assert by_to["s1"].weight == pytest.approx(w1 / (w1 + w2))
    assert by_to["s2"].weight == pytest.approx(w2 / (w1 + w2))


def test_build_gravity_edges_beta_zero_depends_only_on_capacity():
    cfg = make_config(radius_km=200.0, beta=0.0)
    subjects = [
        Subject("d1", "Спрос", "org", 0.0, 0.0, None, None, [Capacity("labor", "demand", 10.0)]),
        Subject("s1", "П1", "org", 0.0, 0.1, None, None, [Capacity("labor", "supply", 25.0)]),
        Subject("s2", "П2", "org", 0.0, 0.5, None, None, [Capacity("labor", "supply", 75.0)]),
    ]

    edges = build_gravity_edges(subjects, cfg)
    by_to = {e.to_id: e.weight for e in edges}

    assert by_to["s1"] == pytest.approx(0.25)
    assert by_to["s2"] == pytest.approx(0.75)


def test_build_gravity_edges_filters_by_radius():
    cfg = make_config(radius_km=20.0, beta=1.0)
    subjects = [
        Subject("d1", "Спрос", "org", 0.0, 0.0, None, None, [Capacity("labor", "demand", 10.0)]),
        Subject("s_in", "В радиусе", "org", 0.0, 0.1, None, None, [Capacity("labor", "supply", 50.0)]),
        Subject("s_out", "За радиусом", "org", 0.0, 1.0, None, None, [Capacity("labor", "supply", 50.0)]),
    ]

    edges = build_gravity_edges(subjects, cfg)

    assert len(edges) == 1
    assert edges[0].to_id == "s_in"
    assert edges[0].weight == pytest.approx(1.0)


def test_build_gravity_edges_no_supplies_within_radius():
    cfg = make_config(radius_km=5.0, beta=2.0)
    subjects = [
        Subject("d1", "Спрос", "org", 0.0, 0.0, None, None, [Capacity("labor", "demand", 10.0)]),
        Subject("s_far", "Далеко", "org", 0.0, 1.0, None, None, [Capacity("labor", "supply", 50.0)]),
    ]
    assert build_gravity_edges(subjects, cfg) == []


def test_build_gravity_edges_same_coordinates_uses_min_visible_distance():
    beta = 2.0
    cfg = make_config(radius_km=50.0, beta=beta)
    subjects = [
        Subject("d1", "Спрос", "org", 30.0, 60.0, None, None, [Capacity("labor", "demand", 10.0)]),
        Subject("s_same", "Тут же", "org", 30.0, 60.0, None, None, [Capacity("labor", "supply", 10.0)]),
        Subject("s_near", "Рядом", "org", 30.0, 60.01, None, None, [Capacity("labor", "supply", 10.0)]),
    ]

    edges = build_gravity_edges(subjects, cfg)
    by_to = {e.to_id: e for e in edges}

    d_near = distance(30.0, 60.0, 30.0, 60.01)
    w_same = 10.0 * (MIN_VISIBLE_DISTANCE ** -beta)
    w_near = 10.0 * (d_near ** -beta)

    assert by_to["s_same"].distance_km == 0.0
    assert by_to["s_same"].weight == pytest.approx(w_same / (w_same + w_near))


def test_build_gravity_edges_multiple_demands_normalized_independently():
    cfg = make_config(radius_km=200.0, beta=2.0)
    subjects = [
        Subject("d1", "Спрос 1", "org", 0.0, 0.0, None, None, [Capacity("labor", "demand", 10.0)]),
        Subject("d2", "Спрос 2", "org", 0.0, 0.5, None, None, [Capacity("labor", "demand", 20.0)]),
        Subject("s1", "П1", "org", 0.0, 0.1, None, None, [Capacity("labor", "supply", 100.0)]),
        Subject("s2", "П2", "org", 0.0, 0.4, None, None, [Capacity("labor", "supply", 100.0)]),
    ]

    edges = build_gravity_edges(subjects, cfg)

    assert len(edges) == 4
    d1_sum = sum(e.weight for e in edges if e.from_id == "d1")
    d2_sum = sum(e.weight for e in edges if e.from_id == "d2")
    assert d1_sum == pytest.approx(1.0)
    assert d2_sum == pytest.approx(1.0)


def test_build_gravity_edges_skips_disabled_domains():
    cfg = make_config(
        radius_km=100.0,
        beta=2.0,
        enabled_domains=["labor"],
        extra_domains={"retail": (100.0, 2.0)},
    )
    subjects = [
        Subject("d1", "D", "org", 0.0, 0.0, None, None, [
            Capacity("labor", "demand", 10.0),
            Capacity("retail", "demand", 10.0),
        ]),
        Subject("s1", "S", "org", 0.0, 0.1, None, None, [
            Capacity("labor", "supply", 50.0),
            Capacity("retail", "supply", 50.0),
        ]),
    ]

    edges = build_gravity_edges(subjects, cfg)
    assert len(edges) == 1
    assert edges[0].domain == "labor"


# updater.py

def test_update_edges_deletes_each_domain_and_inserts():
    repo = MagicMock()
    edges = [Edge("e1", "labor", "d1", "s1", 1.0, 1.0)]

    update_edges(repo, edges, ["labor", "retail"])

    assert repo.mock_calls == [
        call.delete_edges_by_domain("labor"),
        call.delete_edges_by_domain("retail"),
        call.insert_edges(edges),
    ]


def test_update_edges_empty_list_skips_insert():
    repo = MagicMock()

    update_edges(repo, [], ["labor"])

    repo.delete_edges_by_domain.assert_called_once_with("labor")
    repo.insert_edges.assert_not_called()


# equilibrium.py

def test_solve_flows_analytical_single_pair():
    # При t = 0, pc = cc = 10, a = 2.0: 2 * (x / 10)^4 = 2.0 => x = 10.0
    flows = solve_flows(
        supply_caps=np.array([10.0]),
        demand_caps=np.array([10.0]),
        sup_idx=np.array([0]),
        dem_idx=np.array([0]),
        transport_costs=np.array([0.0]),
        max_price=2.0,
        power=4,
    )
    assert flows[0] == pytest.approx(10.0, rel=1e-5)


def test_solve_flows_zero_when_transport_too_high():
    flows = solve_flows(
        supply_caps=np.array([10.0]),
        demand_caps=np.array([10.0]),
        sup_idx=np.array([0]),
        dem_idx=np.array([0]),
        transport_costs=np.array([2.5]),
        max_price=2.0,
    )
    assert flows[0] == pytest.approx(0.0, abs=1e-9)


def test_build_equilibrium_edges_weights_and_distance_preference():
    cfg = make_config(radius_km=200.0)
    cfg.graph = SimpleNamespace(model="equilibrium", max_price=2.0, transport_price=1.5)
    subjects = [
        Subject("d1", "Спрос", "org", 0.0, 0.0, None, None, [Capacity("labor", "demand", 10.0)]),
        Subject("s_near", "Ближний", "org", 0.0, 0.1, None, None, [Capacity("labor", "supply", 10.0)]),
        Subject("s_far", "Дальний", "org", 0.0, 0.5, None, None, [Capacity("labor", "supply", 10.0)]),
    ]

    edges = build_equilibrium_edges(subjects, cfg)

    assert len(edges) == 2
    assert sum(e.weight for e in edges) == pytest.approx(1.0)
    by_to = {e.to_id: e.weight for e in edges}
    assert by_to["s_near"] > by_to["s_far"]


def test_build_equilibrium_edges_empty_or_out_of_radius():
    cfg = make_config(radius_km=5.0)
    cfg.graph = SimpleNamespace(model="equilibrium", max_price=2.0, transport_price=1.0)
    subjects = [
        Subject("d1", "Спрос", "org", 0.0, 0.0, None, None, [Capacity("labor", "demand", 10.0)]),
        Subject("s_far", "Далеко", "org", 0.0, 1.0, None, None, [Capacity("labor", "supply", 10.0)]),
    ]

    assert build_equilibrium_edges([], cfg) == []
    assert build_equilibrium_edges(subjects, cfg) == []


def test_graph_main_selects_equilibrium_model(tmp_path):
    db_file = tmp_path / "db.duckdb"
    db_file.touch()
    cfg = make_config()
    cfg.paths = SimpleNamespace(db=db_file)
    cfg.graph = SimpleNamespace(model="equilibrium")

    with (
        patch.object(graph_main, "get_config", return_value=cfg),
        patch.object(graph_main, "connect"),
        patch.object(graph_main, "Repository"),
        patch.object(graph_main, "build_gravity_edges") as mock_huff,
        patch.object(graph_main, "build_equilibrium_edges", return_value=[]) as mock_eq,
        patch.object(graph_main, "update_edges") as mock_update,
    ):
        graph_main.main()
        mock_huff.assert_not_called()
        mock_eq.assert_called_once()
        mock_update.assert_called_once()


def test_graph_main_unknown_model_exits(tmp_path):
    db_file = tmp_path / "db.duckdb"
    db_file.touch()
    cfg = make_config()
    cfg.paths = SimpleNamespace(db=db_file)
    cfg.graph = SimpleNamespace(model="unknown")

    with (
        patch.object(graph_main, "get_config", return_value=cfg),
        patch.object(graph_main, "connect"),
        patch.object(graph_main, "Repository"),
    ):
        with pytest.raises(SystemExit, match="Unknown graph model: unknown"):
            graph_main.main()


# __main__.py

def test_graph_main_db_not_found(tmp_path):
    cfg = SimpleNamespace(
        paths=SimpleNamespace(db=tmp_path / "missing.duckdb"),
        enabled_domains=["labor"],
    )
    with patch.object(graph_main, "get_config", return_value=cfg):
        with pytest.raises(SystemExit, match="Database not found"):
            graph_main.main()


def test_graph_main_success(tmp_path):
    db_file = tmp_path / "db.duckdb"
    db_file.touch()
    cfg = make_config()
    cfg.paths = SimpleNamespace(db=db_file)

    with (
        patch.object(graph_main, "get_config", return_value=cfg),
        patch.object(graph_main, "connect") as mock_connect,
        patch.object(graph_main, "Repository") as mock_repo_cls,
        patch.object(graph_main, "build_gravity_edges", return_value=[]) as mock_build,
        patch.object(graph_main, "update_edges") as mock_update,
    ):
        graph_main.main()
        mock_connect.assert_called_once_with(read_only=False)
        mock_repo_cls.assert_called_once()
        mock_build.assert_called_once()
        mock_update.assert_called_once()


def test_graph_main_error_exits(tmp_path):
    db_file = tmp_path / "db.duckdb"
    db_file.touch()
    cfg = make_config()
    cfg.paths = SimpleNamespace(db=db_file)

    with (
        patch.object(graph_main, "get_config", return_value=cfg),
        patch.object(graph_main, "connect"),
        patch.object(graph_main, "Repository"),
        patch.object(graph_main, "build_gravity_edges", side_effect=RuntimeError("calc fail")),
    ):
        with pytest.raises(SystemExit, match="Error while building graph: calc fail"):
            graph_main.main()