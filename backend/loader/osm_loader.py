from pathlib import Path
import json
from shapely.geometry import mapping
import osmnx as ox
import pandas as pd
import argparse
from backend.config import get_config

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

def get_data(region=None, full_region=False, save=False, output_path=None):
    """
    Загружает OSM-объекты и возвращает GeoJSON FeatureCollection.

    region: идентификатор региона для поля region.
    full_region: использовать place из конфига вместо тестового bbox.
    save: сохранять ли результат на диск.
    output_path: путь для сохранения результата.
    """

    config = get_config()
    region_id = region or config.region_id

    tags = {
        "amenity": ["bank", "atm"],
        "office": True,
        "shop": True,
        "building": [
            "residential",
            "apartments",
            "house",
            "detached",
            "semidetached_house",
            "terrace",
            "bungalow",
            "dormitory",
            "farm",
        ],
        "place": [
            "city",
            "town",
            "village",
            "hamlet",
            "isolated_dwelling",
        ],
        "man_made": "works",
        "industrial": True,
        "landuse": "industrial",
    }

    if full_region:
        if not config.place:
            raise ValueError(
                "В config/region.yaml не задан region.place."
            )

        gdf = ox.features.features_from_place(
            config.place,
            tags=tags,
        )
    else:
        gdf = ox.features.features_from_bbox(
            bbox=config.test_bbox,
            tags=tags,
        )

    features = []

    for (osm_type, osm_id), row in gdf.iterrows():
        tags_data = {
            key: value
            for key, value in row.items()
            if key != "geometry" and keep_tag(key, value)
        }
        features.append({
            "type": "Feature",
            "id": f"{osm_type}/{osm_id}",
            "properties": {
                "osm_type": str(osm_type),
                "osm_id": int(osm_id),
                "region": region_id,
                "tags": tags_data
            },
            "geometry": (
                mapping(row.geometry)
                if row.geometry is not None
                else None
            ),
        })

    data = {
        "type": "FeatureCollection",
        "features": features,
    }

    if save:
        path = Path(output_path) if output_path else config.paths.raw

        if not path.is_absolute():
            path = Path.cwd() / path
        
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

def get_districts(region=None, full_region=False, save=False, output_path=None):
    """
    Загружает муниципальные районы из OSM

    Ищет административные границы (boundary=administrative) 
    с admin_level=6

    Возвращает отдельный GeoJSON FeatureCollection
    """


    config = get_config()
    region_id = region or config.region_id

    tags = {
        "admin_level": "6",
    }


    if full_region:
        if not config.place:
            raise ValueError(
                "В config/region.yaml не задан region.place."
            )

        gdf = ox.features.features_from_place(
            config.place,
            tags=tags,
        )
    else:
        gdf = ox.features.features_from_bbox(
            bbox=config.test_bbox,
            tags=tags,
        )

    
    features = []

    for (osm_type, osm_id), row in gdf.iterrows():
        # Проверяем условия
        if row.get("boundary") != "administrative":
            continue

        geometry = row.geometry

        if geometry is None or geometry.is_empty:
            continue

        # Для районов ожидаем полигональную геометрию
        if geometry.geom_type not in ("Polygon", "MultiPolygon"):
            continue

        name = None

        for key in (
            "name:ru",
            "name",
            "official_name:ru",
            "official_name",
        ):
            value = row.get(key)

            if isinstance(value, str) and value.strip():
                name = value.strip()
                break

        if name is None:
            name = f"Район OSM {osm_id}"

        tags_data = {
            key: value
            for key, value in row.items()
            if key != "geometry" and keep_tag(key, value)
        }

        features.append({
            "type": "Feature",
            "id": f"{osm_type}/{osm_id}",
            "properties": {
                "id": f"{osm_type}/{osm_id}",
                "name": name,
                "osm_type": str(osm_type),
                "osm_id": int(osm_id),
                "region": region_id,
                "tags": tags_data,
            },
            "geometry": mapping(geometry),
        })

    data = {
        "type": "FeatureCollection",
        "features": features,
    }

    if save:
        path = (
            Path(output_path)
            if output_path
            else config.paths.districts
        )

        if not path.is_absolute():
            path = Path.cwd() / path

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
        description="Загрузка объектов OpenStreetMap"
    )

    parser.add_argument(
        "--region",
        type=str,
        default=None,
        help="Идентификатор региона (по умолчанию из конфига).",
    )

    parser.add_argument(
        "--full-region",
        action="store_true",
        help="Загрузить всю местность из config.region.place.",
    )

    parser.add_argument(
        "--districts-only", 
        action="store_true",
        help="Загрузить только районы."
    )

    parser.add_argument(
        "--save",
        action="store_true",
        help="Сохранить результат в файл.",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Путь к выходному GeoJSON.",
    )

    args = parser.parse_args()

    if not args.districts_only:
        data = get_data(
            region=args.region,
            full_region=args.full_region,
            save=args.save,
            output_path=args.output,
        )

        print(f"Загружено объектов: {len(data['features'])}")

        if args.save:
            config = get_config()
            path = args.output or config.paths.raw

            if not path.is_absolute():
                path = Path.cwd() / path
        
            print(f"Сохранено в: {path.resolve()}")
        else:
            print("Файл не сохранён (--save не указан).")

    districts = get_districts(
        region=args.region,
        full_region=args.full_region,
        save=args.save,
    )

    print(f"Загружено муниципальных районов: {len(districts['features'])}")

    if args.save:
        print("Районы сохранены в: data/raw/districts.json")


if __name__ == "__main__":
    main()