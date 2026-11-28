import argparse
import json
from pathlib import Path

import duckdb
import pandas as pd

from backend.config import get_config
from backend.economy.db import connect, init_schema
from backend.economy.repository import Repository
from backend.economy.models import District
from backend.classification.classifier import load_rules

from tqdm import tqdm

# Сколько строк вставляется одним запросом (пачками, чтобы показывать прогресс и не раздувать память)
BATCH_SIZE = 50_000

KNOWN_TYPES = {r["type"] for r in load_rules()}

VALID_OSM_TYPES = {"node", "way", "relation"}
VALID_DOMAINS = {"money", "labor", "goods"}
VALID_ROLES = {"supply", "demand"}

def validate_feature_collection(data: dict, description: str = "GeoJSON") -> dict:
    """Проверяет структуру GeoJSON FeatureCollection."""
    if not isinstance(data, dict) or data.get("type") != "FeatureCollection":
        raise ValueError(f"Ожидался {description} типа FeatureCollection")

    if not isinstance(data.get("features"), list):
        raise ValueError(f"В {description} отсутствует корректный список features")

    return data

def load_geojson(path: Path):
    """Читает классифицированный GeoJSON из файла."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Файл классифицированных данных не найден: {path}"
        )

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    return validate_feature_collection(data, "классифицированный GeoJSON")

def load_districts_data(data: dict) -> list[District]:
    """Преобразует GeoJSON районов, уже загруженный в память, в список District."""
    validate_feature_collection(data, "GeoJSON районов")

    districts = []
    seen_ids = set()

    for feature in data["features"]:
        properties = feature.get("properties") or {}

        district_id = properties.get("id")
        name = properties.get("name")
        geometry = feature.get("geometry")

        if not district_id:
            raise ValueError("У района отсутствует id.")

        if district_id in seen_ids:
            raise ValueError(f"Повторяется ID района: {district_id}")

        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"У района {district_id} отсутствует название.")

        if not isinstance(geometry, dict):
            raise ValueError(f"У района {district_id} отсутствует геометрия.")

        if geometry.get("type") not in ("Polygon", "MultiPolygon"):
            raise ValueError(
                f"У района {district_id} неподходящий тип геометрии: "
                f"{geometry.get('type')}"
            )

        seen_ids.add(district_id)
        districts.append(District(district_id, name, geometry))

    return districts

def load_districts(path: Path) -> list[District]:
    """Читает GeoJSON районов из файла."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Файл районов не найден: {path}")

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    return load_districts_data(data)

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

    kind = object_type

    if kind is None:
        raise ValueError(
            f"Неизвестный тип классификации {object_type!r} "
            f"у объекта {osm_type}/{osm_id}. "
        )

    if kind not in KNOWN_TYPES:
        raise ValueError(f"Тип {object_type!r} у {osm_type}/{osm_id} отсутствует в rules.yaml")

    group_key = classification.get("group")
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
                group_key,
                rule,
            )
        )

    return rows

def insert_rows(conn, table: str, columns: list[str], rows: list[tuple], select: str = "*") -> None:
    # Вставляет пачку строк одним запросом через DataFrame
    if not rows:
        return
    batch = pd.DataFrame(rows, columns=columns, dtype=object)
    conn.register("_batch", batch)
    try:
        conn.execute(f"INSERT INTO {table} ({', '.join(columns)}) SELECT {select} FROM _batch")
    finally:
        conn.unregister("_batch")

def ingest(
    input_path = None,
    db_path = None,
    districts_path=None,
    data=None,
    districts_data=None,
):
    """
    Загружает классифицированные объекты в DuckDB.

    Данные можно передать напрямую через data и districts_data
    либо прочитать из GeoJSON-файлов через input_path и districts_path.

    Записи объектов региона синхронизируются: старые записи региона
    удаляются, затем вставляются объекты из текущего набора данных.
    """

    config = get_config()

    # Основной GeoJSON: приоритет у данных, переданных в память.
    if data is None:
        input_path = Path(input_path) if input_path else config.paths.classified
        data = load_geojson(input_path)
    else:
        validate_feature_collection(data, "классифицированный GeoJSON")

    # Районы: явно переданные данные имеют приоритет над файлом.
    districts = None
    if districts_data is not None:
        districts = load_districts_data(districts_data)
        if not districts:
            print("Переданный набор районов пуст. Районы не обновлены.")
            districts = None
    else:
        districts_path = (
            Path(districts_path) if districts_path else config.paths.districts
        )
        if not districts_path.is_absolute():
            districts_path = Path.cwd() / districts_path

        if districts_path.exists():
            loaded_districts = load_districts(districts_path)
            if loaded_districts:
                districts = loaded_districts
            else:
                print(
                    f"Файл районов {districts_path} пуст. "
                    "Районы не обновлены."
                )
        else:
            print(
                f"Файл районов {districts_path} не найден. "
                "Районы не обновлены."
            )

    db_path = Path(db_path) if db_path else config.paths.db

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

        # Сначала сохраняем районы
        if districts is not None:
            repository = Repository(conn)
            repository.save_districts(districts)

        # Затем отдельно сохраняем экономические объекты
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

        # Удаляем старые объекты региона
        conn.execute(
            """
            DELETE FROM osm_objects
            WHERE region = ?
            """,
            [region],
        )

        for i in tqdm(range(0, len(objects), BATCH_SIZE), desc="osm_objects"):
            insert_rows(
                conn,
                "osm_objects",
                ["osm_type", "osm_id", "tags", "geom", "region"],
                objects[i:i + BATCH_SIZE],
                select="osm_type, osm_id, CAST(tags AS JSON), ST_GeomFromGeoJSON(geom), region",
            )

        for i in tqdm(range(0, len(classifications), BATCH_SIZE), desc="osm_classifications"):
            insert_rows(
                conn,
                "osm_classification",
                ["osm_type", "osm_id", "domain", "role", "kind", "group_key", "rule"],
                classifications[i:i + BATCH_SIZE],
            )

        conn.execute("COMMIT")

    except Exception:
        try:
            conn.execute("ROLLBACK")
        except duckdb.Error:
            pass
        raise

    finally:
        conn.close()

    return {
        "objects": len(objects),
        "classifications": len(classifications),
        "districts": len(districts) if districts is not None else 0,
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

    parser.add_argument(
        "--districts",
        type=Path,
        default=config.paths.districts,
        help="Путь к GeoJSON муниципальных районов.",
    )

    args = parser.parse_args()

    result = ingest(
        input_path=args.input,
        db_path=args.db,
        districts_path=args.districts,
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
    
    print(
        "Муниципальных районов записано: "
        f"{result['districts']}"
    )

if __name__ == "__main__":
    main()