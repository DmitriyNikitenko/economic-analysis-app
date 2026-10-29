
import json
from collections import Counter
from pathlib import Path

PATH = Path("data/raw/osm_sample.json")


def main():
    data = json.loads(PATH.read_text(encoding="utf-8"))
    features = data.get("features", [])

    print("Всего объектов:", len(features))

    print("\nПо типу OSM:")
    print(dict(Counter(
        feature.get("properties", {}).get("osm_type", "unknown")
        for feature in features
    )))

    print("\nПо типу геометрии:")
    print(dict(Counter(
        feature.get("geometry", {}).get("type", "unknown")
        for feature in features
    )))

    tag_counts = Counter()
    category_counts = Counter()

    for feature in features:
        properties = feature.get("properties", {})

        for key, value in properties.items():
            if key in {"osm_type", "osm_id"}:
                continue

            tag_counts[(key, str(value))] += 1

        # Основные теги для предварительной классификации
        for key in ("amenity", "shop", "office", "place",
                    "landuse", "man_made", "industrial"):
            if key in properties:
                category_counts[(key, str(properties[key]))] += 1

    print("\nСамые частые сочетания тегов:")
    for (key, value), count in tag_counts.most_common(30):
        print(f"{key}={value}: {count}")

    print("\nРаспределение по классификационным тегам:")
    for (key, value), count in category_counts.most_common(30):
        print(f"{key}={value}: {count}")


if __name__ == "__main__":
    main()
