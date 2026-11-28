
import argparse
import json
from pathlib import Path
import random

from backend.config import get_config


def load_geojson(path: Path) -> dict:
    """Загружает классифицированный GeoJSON."""

    if not path.exists():
        raise FileNotFoundError(
            f"Файл не найден: {path}"
        )

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if data.get("type") != "FeatureCollection":
        raise ValueError(
            "Ожидался GeoJSON типа FeatureCollection."
        )

    if not isinstance(data.get("features"), list):
        raise ValueError(
            "В GeoJSON отсутствует список features."
        )

    return data

def print_class_examples(features: list[dict]) -> None:
    examples = {}

    # Собираем все объекты по классам
    grouped = {}

    for feature in features:
        properties = feature.get("properties") or {}
        classification = properties.get("classification") or {}

        if not isinstance(classification, dict):
            continue

        object_type = classification.get("type")

        if not object_type or object_type == "unclassified":
            continue

        grouped.setdefault(object_type, []).append(feature)

    # Выбираем случайный объект каждого класса
    for object_type, objects in grouped.items():
        examples[object_type] = random.choice(objects)

    print("\nПримеры объектов каждого класса")
    print("=" * 60)

    if not examples:
        print("Классифицированные объекты не найдены.")
        return

    for object_type, feature in sorted(examples.items()):
        properties = feature.get("properties") or {}
        classification = properties.get("classification") or {}
        tags = properties.get("tags") or {}

        osm_type = properties.get("osm_type", "unknown")
        osm_id = properties.get("osm_id", "unknown")

        name = (
            tags.get("name:ru")
            or tags.get("name")
            or tags.get("official_name")
            or "Без названия"
        )

        print(f"\nКласс: {object_type}")
        print(f"OSM ID: {osm_type}/{osm_id}")
        print(f"Правило: {classification.get('matched_rule')}")
        print(f"Название: {name}")
        print(f"Домены: {classification.get('domains', [])}")
        print(f"Роли: {classification.get('roles', {})}")
        print("Теги:")
        print(json.dumps(tags, ensure_ascii=False, indent=2))

    print(f"\nВсего классов: {len(examples)}")


def main():
    config = get_config()

    parser = argparse.ArgumentParser(
        description="Просмотр примеров классифицированных OSM-объектов"
    )

    parser.add_argument(
        "--input",
        type=Path,
        default=config.paths.classified,
        help="Путь к классифицированному GeoJSON",
    )

    args = parser.parse_args()

    data = load_geojson(args.input)

    print_class_examples(data["features"])


if __name__ == "__main__":
    main()
