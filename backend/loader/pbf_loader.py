import argparse
import json
from pathlib import Path

import osmium
from shapely.geometry import shape, mapping
from shapely.geometry import box, Point

from backend.config import get_config
from backend.loader.osm_loader import keep_tag

PLACES = {"city", "town", "village", "hamlet", "isolated_dwelling"}
RESIDENTIAL = {"residential", "apartments", "house", "detached",
               "semidetached_house", "terrace", "bungalow", "dormitory", "farm"}



def wanted(t, buildings=True):
    return (
        t.get("amenity") in {"bank", "atm"}
        or "office" in t
        or "shop" in t
        or (buildings and t.get("building") in RESIDENTIAL)
        or t.get("place") in PLACES
        or t.get("man_made") == "works"
        or "industrial" in t
        or t.get("landuse") == "industrial"
    )


def pick_name(t, osm_id):
    for key in ("name:ru", "name", "official_name:ru", "official_name"):
        v = t.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return f"Район OSM {osm_id}"


class Collector(osmium.SimpleHandler):
    def __init__(self, region_id, want_objects=True, buildings=True, bbox=None):
        super().__init__()
        self.region_id = region_id
        self.want_objects = want_objects
        self.factory = osmium.geom.GeoJSONFactory()
        self.objects = []
        self.buildings = buildings
        self.districts = []
        self.region_geoms = []      # границы admin_level=4 для фильтра районов
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
    p.add_argument("--pbf", type=Path, required=True)
    p.add_argument("--region", default=None)
    p.add_argument("--districts-only", action="store_true")
    p.add_argument("--region-name", default="Ярославская область",
                   help="Название admin_level=4 для отсечения чужих районов")
    p.add_argument("--no-buildings", action="store_true",
               help="Не брать жилые здания (для быстрой проверки).")
    p.add_argument("--output", type=Path, default=None,
               help="Куда сохранить объекты (по умолчанию paths.raw).")
    p.add_argument("--bbox", action="store_true",
               help="Ограничить выгрузку test_bbox из конфига.")
    args = p.parse_args()

    region_id = args.region or cfg.region_id
    h = Collector(region_id, want_objects=not args.districts_only,
              buildings=not args.no_buildings,
              bbox=cfg.test_bbox if args.bbox else None)
    # locations=True нужен, чтобы у ways были координаты, иначе area не соберутся
    h.apply_file(str(args.pbf), locations=True, idx="flex_mem")

    # контур области
    region_poly = next((g for name, g in h.region_geoms
                        if args.region_name.lower() in name.lower()), None)
    if region_poly is None:
        print("Контур области (admin_level=4) не найден, районы не фильтруются.")

    features, outside = [], 0
    for osm_id, t, geom in h.districts:
        g = shape(geom)
        if h.bbox is not None and not g.intersects(h.bbox):
            continue
        if region_poly is not None and not g.representative_point().within(region_poly):
            outside += 1
            continue
        name = pick_name(t, osm_id)
        tags = {k: v for k, v in t.items() if keep_tag(k, v)}
        features.append({
            "type": "Feature", "id": f"relation/{osm_id}",
            "properties": {"id": f"relation/{osm_id}", "name": name,
                           "osm_type": "relation", "osm_id": int(osm_id),
                           "region": region_id, "tags": tags},
            "geometry": mapping(g),
        })

    out = write_json({"type": "FeatureCollection", "features": features},
                     cfg.paths.districts)
    print(f"Районов: {len(features)} (отсечено чужих: {outside}) -> {out}")
    for f in sorted(features, key=lambda f: f["properties"]["name"]):
        print("  ", f["properties"]["id"], f["properties"]["name"])

    if not args.districts_only:
        out = write_json({"type": "FeatureCollection", "features": h.objects},
                         cfg.paths.raw)
        print(f"Объектов: {len(h.objects)} -> {out}")
    print(f"Ошибок сборки геометрии: {h.errors}")


if __name__ == "__main__":
    main()