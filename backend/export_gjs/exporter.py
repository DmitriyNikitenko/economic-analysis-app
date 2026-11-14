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
                "district_id": s.district_id,
                "address": s.address,
                "domains": domains
            }
        })
    return {"type": "FeatureCollection", "features": features}


def build_edges_geojson(edges: list[Edge], subjects: list[Subject]) -> dict:
    coords_map = {s.id: [s.lon, s.lat] for s in subjects}

    features = []
    for e in edges:
        if e.from_id not in coords_map or e.to_id not in coords_map:
            raise ValueError(
                f"Integrity error: edge {e.id} references a non-existent node "
                f"(from_id={e.from_id}, to_id={e.to_id})"
            )

        features.append({
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [coords_map[e.from_id], coords_map[e.to_id]]
            },
            "properties": {
                "id": e.id,
                "domain": e.domain,
                "from_id": e.from_id,
                "to_id": e.to_id,
                "distance_km": e.distance_km,
                "weight": e.weight
            }
        })
    return {"type": "FeatureCollection", "features": features}


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

    # Формируем GeoJSON и JSON
    subjects_gjs = build_subjects_geojson(subjects)
    edges_gjs = build_edges_geojson(edges, subjects)
    districts_gjs = build_districts_geojson(districts)
    metrics_json = build_metrics_json(metrics, districts)

    # Пишем файлы для фронтенда
    files = {
        "subjects.geojson": subjects_gjs,
        "edges.geojson": edges_gjs,
        "districts.geojson": districts_gjs,
        "metrics.json": metrics_json
    }

    for filename, data in files.items():
        with open(out_path / filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)