import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import pytest

from backend.economy.models import Capacity, District, Edge, Metric, Subject
from backend.export_gjs import __main__ as export_main
from backend.export_gjs.exporter import (
    build_districts_geojson,
    build_edges_json,
    build_metrics_json,
    build_subjects_geojson,
    run_export,
)
from backend.export_gjs.validator import validate_export_data

SQUARE = {
    "type": "Polygon",
    "coordinates": [[[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0], [0.0, 0.0]]],
}


@pytest.fixture
def sample_data():
    districts = [District("d1", "Центральный", SQUARE)]
    subjects = [
        Subject("s1", "Спрос", "org", "office", 2.0, 2.0, "Адрес 1", "d1", [Capacity("labor", "demand", 10.0)]),
        Subject("s2", "Предложение", "org", "office", 3.0, 3.0, "Адрес 2", "d1", [Capacity("labor", "supply", 20.0)]),
    ]
    edges = [Edge("e1", "labor", "s1", "s2", 1.5, 1.0)]
    metrics = [
        Metric("region", None, "labor", 2, 1, 1.234, False),
        Metric("district", "d1", "labor", 2, 1, 1.0, True),
    ]
    return subjects, edges, districts, metrics


# validator.py

def test_validate_ok(sample_data):
    subjects, edges, districts, _ = sample_data
    validate_export_data(subjects, edges, districts, ["labor"])


def test_validate_empty_lists_ok():
    validate_export_data([], [], [], ["labor"])


def test_validate_demand_without_outgoing_edges_ok():
    d = [District("d1", "Район", SQUARE)]
    s = [Subject("s1", "Спрос", "org", "office", 2.0, 2.0, None, "d1", [Capacity("labor", "demand", 15.0)])]
    validate_export_data(s, [], d, ["labor"])


def test_validate_subject_without_district_ok():
    s = [Subject("s1", "Без района", "org", "office", 99.0, 99.0, None, None, [Capacity("labor", "demand", 10.0)])]
    validate_export_data(s, [], [], ["labor"])


def test_validate_multiple_outgoing_edges_sum_to_one():
    d = [District("d1", "Район", SQUARE)]
    subjects = [
        Subject("s1", "Спрос", "org", "office", 2.0, 2.0, None, "d1", [Capacity("labor", "demand", 10.0)]),
        Subject("s2", "Предложение 1", "org", "office", 3.0, 3.0, None, "d1", [Capacity("labor", "supply", 20.0)]),
        Subject("s3", "Предложение 2", "org", "office", 4.0, 4.0, None, "d1", [Capacity("labor", "supply", 30.0)]),
    ]
    edges = [
        Edge("e1", "labor", "s1", "s2", 1.0, 0.4),
        Edge("e2", "labor", "s1", "s3", 2.0, 0.6),
    ]
    validate_export_data(subjects, edges, d, ["labor"])


def test_validate_duplicate_district_id(sample_data):
    subjects, edges, districts, _ = sample_data
    with pytest.raises(ValueError, match="Duplicate district ID 'd1'"):
        validate_export_data(subjects, edges, districts + districts, ["labor"])


def test_validate_duplicate_subject_id(sample_data):
    subjects, edges, districts, _ = sample_data
    with pytest.raises(ValueError, match="Duplicate subject ID 's1'"):
        validate_export_data(subjects + [subjects[0]], edges, districts, ["labor"])


def test_validate_unknown_district_id():
    d = [District("d1", "Район", SQUARE)]
    s = [Subject("s1", "A", "org", "office", 2.0, 2.0, None, "unknown_d", [Capacity("labor", "demand", 10.0)])]
    with pytest.raises(ValueError, match="unknown district 'unknown_d'"):
        validate_export_data(s, [], d, ["labor"])


def test_validate_subject_disabled_domain():
    d = [District("d1", "Район", SQUARE)]
    s = [Subject("s1", "A", "org", "office", 2.0, 2.0, None, "d1", [Capacity("retail", "demand", 10.0)])]
    with pytest.raises(ValueError, match="disabled domain 'retail'"):
        validate_export_data(s, [], d, ["labor"])


@pytest.mark.parametrize("bad_cap", [0.0, -1.0, -100.5])
def test_validate_bad_capacity(bad_cap):
    d = [District("d1", "Район", SQUARE)]
    s = [Subject("s1", "A", "org", "office", 1.0, 1.0, None, "d1", [Capacity("labor", "demand", bad_cap)])]
    with pytest.raises(ValueError, match="<= 0"):
        validate_export_data(s, [], d, ["labor"])


def test_validate_duplicate_edge_id(sample_data):
    subjects, edges, districts, _ = sample_data
    dup_edges = [edges[0], Edge("e1", "labor", "s1", "s2", 1.5, 0.5)]
    with pytest.raises(ValueError, match="Duplicate edge ID 'e1'"):
        validate_export_data(subjects, dup_edges, districts, ["labor"])


@pytest.mark.parametrize("from_id,to_id", [("missing", "s2"), ("s1", "missing")])
def test_validate_edge_non_existent_node(sample_data, from_id, to_id):
    subjects, _, districts, _ = sample_data
    bad_edges = [Edge("e1", "labor", from_id, to_id, 1.0, 1.0)]
    with pytest.raises(ValueError, match="non-existent node"):
        validate_export_data(subjects, bad_edges, districts, ["labor"])


def test_validate_edge_disabled_domain(sample_data):
    subjects, _, districts, _ = sample_data
    bad_edges = [Edge("e1", "retail", "s1", "s2", 1.0, 1.0)]
    with pytest.raises(ValueError, match="disabled domain 'retail'"):
        validate_export_data(subjects, bad_edges, districts, ["labor"])


@pytest.mark.parametrize("bad_weight", [0.0, -0.1, 1.01, 2.0])
def test_validate_edge_weight_out_of_range(sample_data, bad_weight):
    subjects, _, districts, _ = sample_data
    bad_edges = [Edge("e1", "labor", "s1", "s2", 1.0, bad_weight)]
    with pytest.raises(ValueError, match="outside the range"):
        validate_export_data(subjects, bad_edges, districts, ["labor"])


def test_validate_wrong_from_role(sample_data):
    subjects, _, districts, _ = sample_data
    bad_edges = [Edge("e1", "labor", "s2", "s1", 1.0, 1.0)]
    with pytest.raises(ValueError, match="is not 'demand'"):
        validate_export_data(subjects, bad_edges, districts, ["labor"])


def test_validate_wrong_to_role(sample_data):
    subjects, _, districts, _ = sample_data
    subjects.append(Subject("s3", "Спрос 2", "org", "office", 4.0, 4.0, None, "d1", [Capacity("labor", "demand", 10.0)]))
    bad_edges = [Edge("e1", "labor", "s1", "s3", 1.0, 1.0)]
    with pytest.raises(ValueError, match="is not 'supply'"):
        validate_export_data(subjects, bad_edges, districts, ["labor"])


@pytest.mark.parametrize("weight", [0.5, 0.99, 1.0001])
def test_validate_weights_sum_not_one(sample_data, weight):
    subjects, _, districts, _ = sample_data
    # Для 1.0001 создаём два ребра, чтобы каждое было <= 1.0, но сумма != 1.0
    if weight > 1.0:
        subjects.append(Subject("s3", "П2", "org", "office", 4.0, 4.0, None, "d1", [Capacity("labor", "supply", 10.0)]))
        bad_edges = [
            Edge("e1", "labor", "s1", "s2", 1.0, 0.6),
            Edge("e2", "labor", "s1", "s3", 1.0, 0.6),
        ]
    else:
        bad_edges = [Edge("e1", "labor", "s1", "s2", 1.0, weight)]
    with pytest.raises(ValueError, match="sum of outgoing weights"):
        validate_export_data(subjects, bad_edges, districts, ["labor"])


def test_validate_point_outside_district():
    d = [District("d1", "Район", SQUARE)]
    s = [Subject("s1", "A", "org", "office", 50.0, 50.0, None, "d1", [Capacity("labor", "demand", 10.0)])]
    with pytest.raises(ValueError, match="outside its district"):
        validate_export_data(s, [], d, ["labor"])


# exporter.py

def test_build_subjects_geojson(sample_data):
    subjects, _, _, _ = sample_data
    subj_gjs = build_subjects_geojson(subjects)

    assert subj_gjs["type"] == "FeatureCollection"
    assert len(subj_gjs["features"]) == 2
    f0 = subj_gjs["features"][0]
    assert f0["geometry"] == {"type": "Point", "coordinates": [2.0, 2.0]}
    assert f0["properties"]["id"] == "s1"
    assert f0["properties"]["domains"] == {"labor": {"role": "demand", "capacity": 10.0}}

def test_build_edges_json(sample_data):
    subjects, edges, _, _ = sample_data
    edges_json = build_edges_json(edges, subjects)

    assert edges_json == {
        "labor": {
            "s1": [["s2", 1.0, 1.5]]
        }
    }

@pytest.mark.parametrize("from_id,to_id", [("unknown", "s2"), ("s1", "unknown")])
def test_build_edges_missing_node_raises(sample_data, from_id, to_id):
    subjects, _, _, _ = sample_data
    bad_edges = [Edge("e1", "labor", from_id, to_id, 1.0, 1.0)]
    with pytest.raises(ValueError, match="Integrity error"):
        build_edges_json(bad_edges, subjects)


def test_build_districts_geojson(sample_data):
    _, _, districts, _ = sample_data
    dist_gjs = build_districts_geojson(districts)

    assert dist_gjs["type"] == "FeatureCollection"
    assert dist_gjs["features"][0]["geometry"] == SQUARE
    assert dist_gjs["features"][0]["properties"] == {"id": "d1", "name": "Центральный"}


def test_build_metrics_json_and_unknown_district(sample_data):
    _, _, districts, metrics = sample_data
    metrics.append(Metric("district", "d_missing", "labor", 0, 0, None, True))

    m_json = build_metrics_json(metrics, districts)

    datetime.fromisoformat(m_json["generated_at"])
    assert m_json["region"]["labor"]["avg_degree"] == 1.23
    by_id = {d["id"]: d for d in m_json["districts"]}
    assert by_id["d1"]["name"] == "Центральный"
    assert by_id["d1"]["labor"]["low_data"] is True
    assert by_id["d_missing"]["name"] == "Неизвестный район"
    assert by_id["d_missing"]["labor"]["avg_degree"] == 0.0


def test_run_export_writes_files_and_filters_domains(tmp_path, sample_data):
    subjects, edges, districts, metrics = sample_data
    subjects[0].capacities.append(Capacity("disabled", "demand", -10.0))
    edges.append(Edge("e2", "disabled", "s1", "s2", 1.0, 99.0))

    repo = MagicMock()
    repo.get_subjects.return_value = subjects
    repo.get_edges.return_value = edges
    repo.get_districts.return_value = districts
    repo.get_metrics.return_value = metrics

    out_dir = tmp_path / "export_out"
    run_export(repo, out_dir, ["labor"])

    for name in ("subjects.geojson", "edges.json", "districts.geojson", "metrics.json"):
        assert (out_dir / name).exists()

    saved_edges = json.loads((out_dir / "edges.json").read_text(encoding="utf-8"))
    saved_subjects = json.loads((out_dir / "subjects.geojson").read_text(encoding="utf-8"))
    assert saved_edges == {
        "labor": {
            "s1": [["s2", 1.0, 1.5]]
        }
    }
    assert "disabled" not in saved_subjects["features"][0]["properties"]["domains"]


# __main__.py

def test_export_main_db_not_found(tmp_path):
    cfg = SimpleNamespace(
        paths=SimpleNamespace(db=tmp_path / "no.duckdb", frontend_data=tmp_path),
        enabled_domains=["labor"],
    )
    with patch.object(export_main, "get_config", return_value=cfg):
        with pytest.raises(SystemExit, match="Database not found."):
            export_main.main()


def test_export_main_success(tmp_path):
    db_file = tmp_path / "db.duckdb"
    db_file.touch()
    cfg = SimpleNamespace(
        paths=SimpleNamespace(db=db_file, frontend_data=tmp_path / "out"),
        enabled_domains=["labor"],
    )
    with (
        patch.object(export_main, "get_config", return_value=cfg),
        patch.object(export_main, "connect") as mock_connect,
        patch.object(export_main, "Repository") as mock_repo_cls,
        patch.object(export_main, "run_export") as mock_run,
    ):
        export_main.main()
        mock_connect.assert_called_once_with(read_only=True)
        mock_repo_cls.assert_called_once()
        mock_run.assert_called_once()


def test_export_main_error_exits(tmp_path):
    db_file = tmp_path / "db.duckdb"
    db_file.touch()
    cfg = SimpleNamespace(
        paths=SimpleNamespace(db=db_file, frontend_data=tmp_path / "out"),
        enabled_domains=["labor"],
    )
    with (
        patch.object(export_main, "get_config", return_value=cfg),
        patch.object(export_main, "connect"),
        patch.object(export_main, "Repository"),
        patch.object(export_main, "run_export", side_effect=ValueError("bad data")),
    ):
        with pytest.raises(SystemExit, match="Error while exporting data: bad data"):
            export_main.main()