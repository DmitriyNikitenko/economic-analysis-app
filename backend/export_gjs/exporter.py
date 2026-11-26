import json
from datetime import datetime
from pathlib import Path
from backend.economy.models import Subject, Edge, District, Metric
from backend.economy.repository import Repository
from backend.export_gjs.validator import validate_export_data


def build_subjects_geojson(subjects: list[Subject]) -> dict:
    features = []
    for s in subjects:
        domains = {
            c.domain: {"role": c.role, "capacity": c.capacity}
            for c in s.capacities
        }

        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [s.lon, s.lat]
            },
            "properties": {
                "id": s.id,
                "name": s.name,
                "kind": s.kind,
                "group": s.group,
                "district_id": s.district_id,
                "address": s.address,
                "domains": domains
            }
        })
    return {"type": "FeatureCollection", "features": features}


def build_edges_json(edges: list[Edge], subjects: list[Subject]) -> dict:
    subject_ids = {s.id for s in subjects}

    result: dict[str, dict[str, list[list]]] = {}
    for e in edges:
        if e.from_id not in subject_ids or e.to_id not in subject_ids:
            raise ValueError(
                f"Integrity error: edge {e.id} references a non-existent node "
                f"(from_id={e.from_id}, to_id={e.to_id})"
            )

        domain_map = result.get(e.domain)
        if domain_map is None:
            domain_map = {}
            result[e.domain] = domain_map

        outgoing = domain_map.get(e.from_id)
        if outgoing is None:
            outgoing = []
            domain_map[e.from_id] = outgoing

        outgoing.append([e.to_id, round(e.weight, 6), round(e.distance_km, 3)])

    return result


def build_districts_geojson(districts: list[District]) -> dict:
    features = []
    for d in districts:
        features.append({
            "type": "Feature",
            "geometry": d.geom,
            "properties": {
                "id": d.id,
                "name": d.name
            }
        })
    return {"type": "FeatureCollection", "features": features}


def build_metrics_json(metrics: list[Metric], districts: list[District]) -> dict:
    # Собираем словарь названий районов
    district_names = {d.id: d.name for d in districts}

    res_region = {}
    districts_map = {}

    for m in metrics:
        safe_avg = round(m.avg_degree, 2) if m.avg_degree is not None else 0.0

        metric_data = {
            "node_count": m.node_count,
            "edge_count": m.edge_count,
            "avg_degree": safe_avg,
            "low_data": bool(m.low_data)
        }

        if m.scope == "region":
            res_region[m.domain] = metric_data
        elif m.scope == "district" and m.district_id:
            d_id = m.district_id
            if d_id not in districts_map:
                districts_map[d_id] = {
                    "id": d_id,
                    "name": district_names.get(d_id, "Неизвестный район")
                }
            districts_map[d_id][m.domain] = metric_data
    return {
        "generated_at": datetime.now().astimezone().replace(microsecond=0).isoformat(),
        "region": res_region,
        "districts": list(districts_map.values())
    }


def _write_json(path: Path, data: dict, *, compact: bool = True) -> None:
    with open(path, "w", encoding="utf-8") as f:
        if compact:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(data, f, ensure_ascii=False, indent=2)


def run_export(repo: Repository, output_dir: str | Path, enabled_domains: list[str]) -> None:
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # Запрашиваем все данные из DuckDB
    subjects = repo.get_subjects()
    edges = repo.get_edges()
    districts = repo.get_districts()
    metrics = repo.get_metrics()

    # Удаляем отключенные домены
    active_domains = set(enabled_domains)
    edges = [e for e in edges if e.domain in active_domains]
    for s in subjects:
        s.capacities = [c for c in s.capacities if c.domain in active_domains]

    # Проверяем целостность данных
    validate_export_data(subjects, edges, districts, enabled_domains)

    # Формируем и пишем файлы по очереди, не держа все словари в памяти одновременно
    _write_json(out_path / "subjects.geojson", build_subjects_geojson(subjects))
    _write_json(out_path / "edges.json", build_edges_json(edges, subjects))
    _write_json(out_path / "districts.geojson", build_districts_geojson(districts))
    _write_json(out_path / "metrics.json", build_metrics_json(metrics, districts), compact=False)