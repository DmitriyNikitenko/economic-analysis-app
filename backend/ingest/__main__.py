import argparse
import json
from pathlib import Path
from typing import Any

from backend.config import get_config
from backend.economy.db import connect, init_schema

# Упрощенные категории (временно)
KIND_MAPPING = {
    "bank": "bank",
    "atm": "bank",
    "financial_service": "bank",

    "settlement": "settlement",

    "industrial_area": "employer",
    "industrial_facility": "employer",
    "employer": "employer",

    "shop": "shop",
    "service": "shop",
}

VALID_OSM_TYPES = {"node", "way", "relation"}
VALID_DOMAINS = {"money", "labor", "goods"}
VALID_ROLES = {"supply", "demand"}

def load_geojson(path: Path):
    """Читает классифицированный GeoJSON"""
    if not path.exists():
        raise FileNotFoundError(
            f"Файл классифицированных данных не найден: {path}"
        )

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if data.get("type") != "FeatureCollection":
        raise ValueError(
            "Ожидался GeoJSON типа FeatureCollection"
        )

    if not isinstance(data.get("features"), list):
        raise ValueError(
            "В GeoJSON отсутствует корректный список features"
        )

    return data

def get_object_data(feature):
    """
    Извлекает данные OSM-объекта из GeoJSON Feature

    Ожидаемая структура properties:
    {
        "osm_type": "node",
        "osm_id": 123,
        "region": "yaroslavl",
        "tags": {...},
        "classification": {...}
    }
    """

    properties = feature.get("properties") or {}

    osm_type = properties.get("osm_type")
    osm_id = properties.get("osm_id")
    region = properties.get("region")
    tags = properties.get("tags") or {}
    geometry = feature.get("geometry")

    if osm_type not in VALID_OSM_TYPES:
        raise ValueError(
            f"Некорректный osm_type: {osm_type!r}"
        )

    if osm_id is None:
        raise ValueError("У объекта отсутствует osm_id.")

    if not isinstance(tags, dict):
        raise ValueError(
            f"Теги объекта {osm_type}/{osm_id} должны быть словарём."
        )

    if not isinstance(region, str) or not region.strip():
        raise ValueError(
            f"У объекта {osm_type}/{osm_id} не задан регион."
        )

    if not isinstance(geometry, dict):
        raise ValueError(
            f"У объекта {osm_type}/{osm_id} отсутствует геометрия."
        )

    return {
        "osm_type": osm_type,
        "osm_id": int(osm_id),
        "region": region,
        "tags": tags,
        "geometry": geometry,
        "classification": properties.get("classification") or {},
    }

def prepare_classification(
    osm_type,
    osm_id,
    classification,
):
    """
    Преобразует результат классификации в строки
    для таблицы osm_classification.

    Одна строка соответствует одному домену объекта.
    """

    object_type = classification.get("type", "unclassified")

    # Неклассифицированные объекты остаются в osm_objects,
    # но не получают записей в osm_classification.
    if object_type == "unclassified":
        return []

    kind = KIND_MAPPING.get(object_type)

    if kind is None:
        raise ValueError(
            f"Неизвестный тип классификации {object_type!r} "
            f"у объекта {osm_type}/{osm_id}. "
        )

    domains = classification.get("domains") or []
    roles = classification.get("roles") or {}
    rule = classification.get("matched_rule")

    if not isinstance(domains, list):
        raise ValueError(
            f"domains должен быть списком у объекта {osm_type}/{osm_id}."
        )

    if not isinstance(roles, dict):
        raise ValueError(
            f"roles должен быть словарём у объекта {osm_type}/{osm_id}."
        )

    rows = []

    for domain in domains:
        if domain not in VALID_DOMAINS:
            raise ValueError(
                f"Неизвестный домен {domain!r} "
                f"у объекта {osm_type}/{osm_id}."
            )

        role = roles.get(domain)

        if role not in VALID_ROLES:
            raise ValueError(
                f"Некорректная роль {role!r} для домена {domain!r} "
                f"у объекта {osm_type}/{osm_id}."
            )

        rows.append(
            (
                osm_type,
                osm_id,
                domain,
                role,
                kind,
                rule,
            )
        )

    return rows

def ingest(
    input_path = None,
    db_path = None,
):
    """
    Загружает классифицированные объекты в DuckDB.

    Данные региона синхронизируются:
    старые записи региона удаляются, затем вставляются
    объекты из текущего GeoJSON.
    """

    config = get_config()

    input_path = input_path or config.paths.classified
    db_path = db_path or config.paths.db

    data = load_geojson(input_path)

    objects = []
    classifications = []

    for feature in data["features"]:
        obj = get_object_data(feature)

        objects.append(
            (
                obj["osm_type"],
                obj["osm_id"],
                json.dumps(
                    obj["tags"],
                    ensure_ascii=False,
                ),
                json.dumps(
                    obj["geometry"],
                    ensure_ascii=False,
                ),
                obj["region"],
            )
        )

        classifications.extend(
            prepare_classification(
                obj["osm_type"],
                obj["osm_id"],
                obj["classification"],
            )
        )

    regions = {obj[4] for obj in objects}

    if not regions:
        raise ValueError(
            "В GeoJSON нет объектов для загрузки."
        )

    if len(regions) != 1:
        raise ValueError(
            "В одном запуске ожидаются объекты только одного региона. "
            f"Обнаружены регионы: {sorted(regions)}"
        )

    region = next(iter(regions))

    conn = connect(db_path)

    try:
        init_schema(conn)

        conn.execute("BEGIN TRANSACTION")

        # Удаляем старую классификацию объектов этого региона.
        conn.execute(
            """
            DELETE FROM osm_classification
            WHERE EXISTS (
                SELECT 1
                FROM osm_objects
                WHERE osm_objects.osm_type =
                      osm_classification.osm_type
                  AND osm_objects.osm_id =
                      osm_classification.osm_id
                  AND osm_objects.region = ?
            )
            """,
            [region],
        )

        # Удаляем старые объекты региона.
        # Это также удалит объекты, которых больше нет в GeoJSON.
        conn.execute(
            """
            DELETE FROM osm_objects
            WHERE region = ?
            """,
            [region],
        )

        # Записываем исходные OSM-объекты.
        conn.executemany(
            """
            INSERT OR REPLACE INTO osm_objects (
                osm_type,
                osm_id,
                tags,
                geom,
                region
            )
            VALUES (
                ?, ?, CAST(? AS JSON), ST_GeomFromGeoJSON(?), ?
            )
            """,
            objects,
        )

        # Записываем классификацию:
        # одна запись на каждый домен объекта.
        if classifications:
            conn.executemany(
                """
                INSERT OR REPLACE INTO osm_classification (
                    osm_type,
                    osm_id,
                    domain,
                    role,
                    kind,
                    rule
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                classifications,
            )

        conn.execute("COMMIT")

    except Exception:
        conn.execute("ROLLBACK")
        raise

    finally:
        conn.close()

    return {
        "objects": len(objects),
        "classifications": len(classifications),
        "unclassified": sum(
            1
            for feature in data["features"]
            if (
                (feature.get("properties") or {})
                .get("classification", {})
                .get("type", "unclassified")
                == "unclassified"
            )
        ),
    }

def main():
    config = get_config()

    parser = argparse.ArgumentParser(
        description="Загрузка классифицированных OSM-объектов в DuckDB"
    )

    parser.add_argument(
        "--input",
        type=Path,
        default=config.paths.classified,
        help="Путь к классифицированному GeoJSON",
    )

    parser.add_argument(
        "--db",
        type=Path,
        default=config.paths.db,
        help="Путь к файлу DuckDB",
    )

    args = parser.parse_args()

    result = ingest(
        input_path=args.input,
        db_path=args.db,
    )

    print("Загрузка завершена.")
    print(f"Объектов записано: {result['objects']}")
    print(
        "Записей классификации: "
        f"{result['classifications']}"
    )
    print(
        "Неклассифицированных объектов: "
        f"{result['unclassified']}"
    )


if __name__ == "__main__":
    main()