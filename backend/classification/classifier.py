import argparse
import copy
import json
from pathlib import Path
from collections import Counter
import yaml

from backend.config import get_config

def load_rules(rules_path=None):
    """Загружает правила классификации из YAML"""
    config = get_config()
    path = Path(rules_path) if rules_path else config.paths.rules

    if not path.is_absolute():
        path = Path.cwd() / path

    rules_data = yaml.safe_load(path.read_text(encoding="utf-8"))

    if not isinstance(rules_data, dict) or not isinstance(
        rules_data.get("rules"), list
    ):
        raise ValueError("Некорректный файл правил: ожидается список rules.")

    return rules_data["rules"]

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
    """Классифицирует один объект по его OSM-тегам."""
    tags = properties.get("tags", properties)
    
    matched = [
        rule for rule in rules
        if matches(tags, rule["match"])
    ]
    
    matched.sort(
        key=lambda rule: rule.get("priority", 0), 
        reverse=True
    )

    if not matched:
        return {
            "type": "unclassified",
            "domains": [],
            "roles": {},
            "matched_rule": None,
        }

    # Первое правило определяет основную категорию.
    matched_rule = matched[0]

    return {
        "type": matched_rule["type"],
        "domains": matched_rule.get("domains", []),
        "roles": matched_rule.get("roles", {}),
        "matched_rule": matched_rule,
    }

def classify_data(data=None, rules=None, save=False, input_path=None, output_path=None):
    config = get_config()
    
    if data is None:
        path = Path(input_path) if input_path else config.paths.raw
        if not path.is_absolute():
            path = Path.cwd() / path
        data = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(data, dict) or data.get("type") != "FeatureCollection":
        raise ValueError(
            "Ожидается GeoJSON-объект типа FeatureCollection."
        )

    if rules is None:
        rules = load_rules()

    result = copy.deepcopy(data)

    for feature in result.get("features", []):
        properties = feature.setdefault("properties", {})
        properties["classification"] = classify(properties, rules)

    if save:
        path = Path(output_path) if output_path else config.paths.classified
        if not path.is_absolute():
            path = Path.cwd() / path
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
    config = get_config()

    parser = argparse.ArgumentParser(
        description="Классификация объектов OpenStreetMap"
    )

    parser.add_argument(
        "--input",
        type=Path,
        default=config.paths.raw,
        help="Входной JSON",
    )

    parser.add_argument(
        "--save",
        action="store_true",
        help="Сохранить результат",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=config.paths.classified,
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
        print(f"Сохранено в: {args.output.resolve()}")
    else:
        print("Файл не сохранён (--save не указан).")

if __name__ == "__main__":
    main()
