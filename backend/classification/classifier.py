import argparse
import copy
import json
from pathlib import Path
import yaml
from collections import Counter

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "data/raw/osm_sample.json"
RULES_FILE = ROOT / "backend/classification/rules.yaml"
OUTPUT = ROOT / "data/processed/osm_classified.json"

def matches(properties, conditions):
    """Проверяет, соответствует ли объект всем условиям правила."""
    for key, expected in conditions.items():
        actual = properties.get(key)

        if actual is None:
            return False

        if expected == "*":
            if str(actual).strip() == "":
                return False
        elif isinstance(expected, list):
            if actual not in expected:
                return False
        elif actual != expected:
            return False

    return True

def classify(properties, rules):
    """Возвращает основную категорию и список сработавших правил."""
    matched = [
        rule for rule in rules
        if matches(properties, rule["match"])
    ]
    matched.sort(key=lambda rule: rule.get("priority", 0), reverse=True)

    if not matched:
        return {
            "type": "unclassified",
            "domains": [],
            "roles": {},
            "matched_rules": [],
        }

    # Первое правило определяет основную категорию.
    primary = matched[0]

    return {
        "type": primary["type"],
        "domains": primary.get("domains", []),
        "roles": primary.get("roles", {}),
        "matched_rules": [rule["id"] for rule in matched],
    }

def classify_data(data=None, save=False, input_path=None, output_path=None):
    if data is None:
        path = Path(input_path) if input_path else INPUT
        if not path.is_absolute():
            path = ROOT / path
        data = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(data, dict) or data.get("type") != "FeatureCollection":
        raise ValueError(
            "Ожидается GeoJSON-объект типа FeatureCollection."
        )
    
    rules_data = yaml.safe_load(RULES_FILE.read_text(encoding="utf-8"))
    rules = rules_data["rules"]

    result = copy.deepcopy(data)
    features = result.get("features", [])

    for feature in features:
        properties = feature.setdefault("properties", {})
        properties["classification"] = classify(properties, rules)

    if save:
        path = Path(output_path) if output_path else OUTPUT
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return result

def get_summary(data):
    """Возвращает статистику по типам классификации."""
    counts = Counter(
        feature.get("properties", {})
        .get("classification", {})
        .get("type", "unclassified")
        for feature in data.get("features", [])
    )

    return {
        "total": len(data.get("features", [])),
        "by_type": dict(counts.most_common()),
    }

def main():
    parser = argparse.ArgumentParser(
        description="Классификация объектов OpenStreetMap."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=INPUT,
        help="Входной JSON.",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Сохранить классифицированный GeoJSON.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT,
        help="Путь к выходному GeoJSON.",
    )
    args = parser.parse_args()

    data = classify_data(
        input_path=args.input,
        save=args.save,
        output_path=args.output,
    )

    summary = get_summary(data)
    print(f"Обработано объектов: {summary['total']}")
    print("Результаты классификации:")

    for category, count in summary["by_type"].items():
        print(f"  {category}: {count}")

    if args.save:
        path = args.output
        print(f"Сохранено в: {path.resolve()}")
    else:
        print("Файл не сохранён (--save не указан).")

if __name__ == "__main__":
    main()
