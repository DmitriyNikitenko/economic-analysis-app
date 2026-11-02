from pathlib import Path
import json
from shapely.geometry import mapping
import osmnx as ox
import pandas as pd
import argparse

# На первом этапе скачиваем только объекты,
# полезные для анализа экономической активности.
TAGS = {
    "amenity": ["bank", "atm"],
    "office": True,
    "shop": True,
    "place": [
        "city", "town", "village",
        "hamlet", "isolated_dwelling"
    ],
    "man_made": "works",
    "industrial": True,
    "landuse": "industrial",
}

OUTPUT = Path("data/raw/osm_sample.json")

NAME_KEYS = {"name", "alt_name", "official_name", "short_name", "old_name"}
KEEP_LANGS = {"ru", "en"}

def keep_tag(key, value):
    """Оставляет только заполненные свойства и нужные языки названий."""
    if value is None:
        return False

    if not isinstance(value, (list, dict)) and pd.isna(value):
        return False
    
    if isinstance(value, str) and not value.strip():
        return False

    # Удаляем name:de, alt_name:fr и подобные языковые варианты,
    # оставляя name:ru, name:en, alt_name:ru и т. д.
    for name_key in NAME_KEYS:
        prefix = f"{name_key}:"
        if key.startswith(prefix):
            language = key[len(prefix):].split(":")[0].split("-")[0]
            return language in KEEP_LANGS
    return True

def get_data(save=False, output_path=None):
    # Небольшой участок Ярославля для тестирования.

    bbox = (39.86, 57.61, 39.92, 57.64)

    gdf = ox.features.features_from_bbox(
        bbox=bbox,
        tags=TAGS,
    )
                       
    # gdf = ox.features_from_place(
    #     "Ярославская область, Россия",
    #     tags=TAGS,
    # )

    features = []

    for (osm_type, osm_id), row in gdf.iterrows():
        properties = {
            key: value
            for key, value in row.items()
            if key != "geometry" and keep_tag(key, value)
        }
        features.append({
            "type": "Feature",
            "id": f"{osm_type}/{osm_id}",
            "properties": {
                "osm_type": osm_type,
                "osm_id": int(osm_id),
                **properties,
            },
            "geometry": mapping(row.geometry),
        })

    data = {
        "type": "FeatureCollection",
        "features": features,
    }

    if save:
        path = Path(output_path) if output_path else OUTPUT

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                data,
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )

    return data

def main():
    parser = argparse.ArgumentParser(
        description="Загрузка объектов OpenStreetMap в JSON."
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Сохранить результат в файл.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT,
        help="Путь к выходному GeoJSON.",
    )
    args = parser.parse_args()

    data = get_data(
        save=args.save,
        output_path=args.output,
    )

    print(f"Загружено объектов: {len(data['features'])}")

    if args.save:
        path = args.output
        print(f"Сохранено в: {path.resolve()}")
    else:
        print("Файл не сохранён (--save не указан).")


if __name__ == "__main__":
    main()