import json
from pathlib import Path
import yaml

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


def classify_data():
    data = json.loads(INPUT.read_text(encoding="utf-8"))
    rules_data = yaml.safe_load(RULES_FILE.read_text(encoding="utf-8"))
    rules = rules_data["rules"]

    for feature in data.get("features", []):
        properties = feature.setdefault("properties", {})
        properties["classification"] = classify(properties, rules)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    features = data.get("features", [])
    print(f"Обработано объектов: {len(features)}")

    from collections import Counter

    counts = Counter(
        feature["properties"]["classification"]["type"]
        for feature in features
    )

    print("Результаты классификации:")
    for category, count in counts.most_common():
        print(f"  {category}: {count}")

    print(f"Сохранено в: {OUTPUT}")


if __name__ == "__main__":
    classify_data()
