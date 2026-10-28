import json
from pathlib import Path
from backend.economy.db import connect
from backend.economy.repository import OsmObjectRepository


def export_osm_to_geojson(output_path: str | Path = "data/osm_objects.geojson", region: str | None = None) -> None:
    # Открываем соединение с базой
    con = connect(read_only=True)
    repo = OsmObjectRepository(con)

    # Получаем готовые объекты OsmObject
    objects = repo.find_by_region(region) if region else repo.find_all()

    features = []
    for obj in objects:
        # Собираем структуру Feature для каждого объекта
        feature = {
            "type": "Feature",
            "geometry": obj.geometry,
            "properties": {
                "osm_type": obj.osm_type,
                "osm_id": obj.osm_id,
                "kind": obj.kind,
                "tags": obj.tags,
                "roles": [
                    {
                        "domain": r.domain,
                        "role": r.role,
                        "rule": r.rule
                    }
                    for r in obj.roles  # Роли из доменов
                ]
            }
        }
        features.append(feature)

    # Формируем итоговый FeatureCollection
    feature_collection = {
        "type": "FeatureCollection",
        "features": features
    }

    # Записываем в статический файл для фронтенда
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(
        json.dumps(feature_collection, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

if __name__ == "__main__":
    export_osm_to_geojson()