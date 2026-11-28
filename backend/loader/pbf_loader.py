import argparse
import json
from pathlib import Path

import osmium

from shapely.geometry import shape, mapping, box, Point

from backend.config import get_config
from backend.loader.osm_tags import (
    keep_tag,
    pick_name,
    PLACES,
    RESIDENTIAL,
    FOOD_SHOPS,
    LARGE_RETAIL,
    PERSONAL_SERVICES,
    FOOD_SERVICES,
)

def wanted(tags, buildings=True):
    """
    Проверяет, соответствует ли объект хотя бы одному
    правилу из rules.yaml.
    """
    # Финансы
    if tags.get("amenity") in {"bank", "atm"}:
        return True

    if tags.get("shop") in {"money_lender", "pawnbroker"}:
        return True

    if tags.get("office") == "financial":
        return True

    # Населённые пункты
    if tags.get("place") in PLACES:
        return True

    # Жилые здания
    if buildings and tags.get("building") in RESIDENTIAL:
        return True

    # Промышленность
    if tags.get("man_made") == "works":
        return True

    if tags.get("landuse") == "industrial":
        return True

    if tags.get("industrial"):
        return True

    # Офисы
    if tags.get("office"):
        return True

    # Торговля
    if tags.get("shop"):
        return True

    # Услуги
    if tags.get("amenity") in FOOD_SERVICES:
        return True

    return False

class Collector(osmium.SimpleHandler):
    def __init__(self, region_id, want_objects=True, buildings=True, bbox=None):
        super().__init__()
        self.region_id = region_id
        self.want_objects = want_objects
        self.buildings = buildings
        self.factory = osmium.geom.GeoJSONFactory()
        self.objects = []
        self.districts = []
        self.region_geoms = []
        self.errors = 0
        self.bbox = box(*bbox) if bbox else None

    def _feature(self, osm_type, osm_id, tags, geometry, extra=None):
        tags = {k: v for k, v in tags.items() if keep_tag(k, v)}
        props = {"osm_type": osm_type, "osm_id": int(osm_id),
                 "region": self.region_id, "tags": tags}
        if extra:
            props.update(extra)
        return {"type": "Feature", "id": f"{osm_type}/{osm_id}",
                "properties": props, "geometry": geometry}

    def node(self, n):
        if not self.want_objects or not n.tags:
            return
        if self.bbox is not None and not self.bbox.contains(Point(n.location.lon, n.location.lat)):
            return
        t = {tag.k: tag.v for tag in n.tags}
        if wanted(t, self.buildings):
            geom = json.loads(self.factory.create_point(n))
            self.objects.append(self._feature("node", n.id, t, geom))

    def area(self, a):
        t = {tag.k: tag.v for tag in a.tags}
        is_relation = not a.from_way()
        osm_id = a.orig_id()

        # границы (районы и контур области)
        if t.get("boundary") == "administrative" and is_relation:
            level = t.get("admin_level")
            if level in ("4", "6"):
                try:
                    geom = json.loads(self.factory.create_multipolygon(a))
                    g = shape(geom)
                    if self.bbox is not None and not g.intersects(self.bbox):
                        return
                except Exception:
                    self.errors += 1
                    print(f"Не собрался полигон: relation/{osm_id} {t.get('name')}")
                    return
                if level == "4":
                    self.region_geoms.append((t.get("name", ""), shape(geom)))
                else:
                    self.districts.append((osm_id, t, geom))
            return

        if not self.want_objects or not wanted(t, self.buildings):
            return
        try:
            geom = json.loads(self.factory.create_multipolygon(a))
            if self.bbox is not None and not shape(geom).intersects(self.bbox):
                return
        except Exception as e:
            self.errors += 1
            if self.errors <= 5:
                print(f"Ошибка геометрии {osm_id}: {e!r}")
            return
        self.objects.append(self._feature(
            "relation" if is_relation else "way", osm_id, t, geom))

def load_pbf(
    pbf_path,
    region=None,
    region_name="Ярославская область",
    bbox=None,
    districts_only=False,
    buildings=True,
):
    """
    Загружает данные OSM из PBF.

    Args:
        pbf_path: путь к PBF-файлу.
        region: идентификатор региона.
        region_name: название области для поиска admin_level=4.
        bbox: ограничить загрузку тестовым bbox из конфига.
        districts_only: загружать только районы.
        buildings: загружать жилые здания.

    Returns:
        tuple:
            raw_data: FeatureCollection объектов OSM.
            districts_data: FeatureCollection районов.
            stats: статистика загрузки.
    """

    config = get_config()

    pbf_path = Path(pbf_path)

    if not pbf_path.exists():
        raise FileNotFoundError(
            f"PBF-файл не найден: {pbf_path}"
        )

    if pbf_path.suffix.lower() != ".pbf":
        raise ValueError(
            f"Ожидается файл с расширением .pbf: {pbf_path}"
        )

    region_id = region or config.region_id

    collector = Collector(
        region_id,
        want_objects=not districts_only,
        buildings=buildings,
        bbox=config.test_bbox if bbox is None else bbox,
    )

    print(f"Загрузка PBF: {pbf_path}")

    # locations=True необходим для сборки геометрий ways.
    collector.apply_file(
        str(pbf_path),
        locations=True,
        idx="flex_mem",
    )

    # Поиск контура области
    region_poly = next(
        (
            geom
            for name, geom in collector.region_geoms
            if region_name.lower() in name.lower()
        ),
        None,
    )

    if region_poly is None:
        print(
            "Контур области (admin_level=4) не найден, "
            "районы не фильтруются."
        )

    # Формирование GeoJSON районов
    district_features = []
    outside = 0

    for osm_id, tags, geometry in collector.districts:

        geom = shape(geometry)

        if (
            collector.bbox is not None
            and not geom.intersects(collector.bbox)
        ):
            continue

        if (
            region_poly is not None
            and not geom.representative_point().within(region_poly)
        ):
            outside += 1
            continue

        name = pick_name(tags, osm_id)

        filtered_tags = {
            k: v
            for k, v in tags.items()
            if keep_tag(k, v)
        }

        district_features.append({
            "type": "Feature",
            "id": f"relation/{osm_id}",
            "properties": {
                "id": f"relation/{osm_id}",
                "name": name,
                "osm_type": "relation",
                "osm_id": int(osm_id),
                "region": region_id,
                "tags": filtered_tags,
            },
            "geometry": mapping(geom),
        })

    raw_data = {
        "type": "FeatureCollection",
        "features": (
            [] if districts_only else collector.objects
        ),
    }

    districts_data = {
        "type": "FeatureCollection",
        "features": district_features,
    }

    stats = {
        "objects": len(raw_data["features"]),
        "districts": len(district_features),
        "districts_outside": outside,
        "geometry_errors": collector.errors,
    }

    print(f"Объектов: {stats['objects']}")
    print(
        f"Районов: {stats['districts']} "
        f"(отсечено чужих: {outside})"
    )
    print(
        f"Ошибок сборки геометрии: "
        f"{stats['geometry_errors']}"
    )

    return raw_data, districts_data, stats

def write_json(data, path):
    path = Path(path)
    if not path.is_absolute():
        path = Path.cwd() / path
    path.parent.mkdir(parents=True, exist_ok=True)
    # без indent: файл получается в несколько раз меньше
    path.write_text(json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8")
    return path


def main():
    cfg = get_config()
    p = argparse.ArgumentParser(description="Загрузка данных OSM из PBF")
    p.add_argument("--pbf", type=Path, required=True, help="Путь к PBF-файлу.")
    p.add_argument("--region", default=None, help="Идентификатор региона.")
    p.add_argument("--districts-only", action="store_true")
    p.add_argument("--region-name", default="Ярославская область",
                   help="Название admin_level=4 для отсечения чужих районов")
    p.add_argument("--no-buildings", action="store_true",
               help="Не брать жилые здания (для быстрой проверки).")
    p.add_argument("--output", type=Path, default=None,
               help="Куда сохранить объекты (по умолчанию paths.raw).")
    args = p.parse_args()

    raw_data, districts_data, stats = load_pbf(
        pbf_path=args.pbf,
        region=args.region,
        region_name=args.region_name,
        districts_only=args.districts_only,
        buildings=not args.no_buildings,
    )

    # Сохранение районов
    districts_path = write_json(
        districts_data,
        cfg.paths.districts,
    )

    print(f"Районы сохранены: {districts_path}")

        # Сохранение объектов
    if not args.districts_only:

        output_path = (
            args.output
            if args.output is not None
            else cfg.paths.raw
        )

        output_path = write_json(
            raw_data,
            output_path,
        )

        print(f"Объекты сохранены: {output_path}")

if __name__ == "__main__":
    main()