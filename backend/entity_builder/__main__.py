# Сборщик сущностей: превращает классифицированные объекты OSM в таблицу subjects и capacities
# loader -> classifier -> ingest -> entity_builder -> graph -> metrics -> export
#
# Как считается ёмкость:
#   residence) - площадь* этажность
#   bank, employer и остальные - средняя ёмкость жилых домов
#   settlement  - справочный объект: субъект есть, ёмкостей нет
import json
import math
import re
from shapely.affinity import scale
from shapely.geometry import shape
from backend.config import get_config
from backend.economy.db import connect, init_schema
from backend.economy.models import Capacity, Subject
from backend.economy.repository import Repository

RESIDENCE = "residence"
NO_CAPACITY_KINDS = {"settlement"} 

# Ёмкость, если её не из чего посчитать (например, в данных вообще нет жилых домов).
DEFAULT_CAPACITY = 1.0
DEFAULT_LEVELS = 1  # этажность, если в OSM не указан building:levels

# Длина одного градуса дуги в метрах; радиус Земли 6371 км, как в backend/graph/engine.py
METERS_PER_DEGREE = 111_195

def fetch_rows(con, region_id: str, domains: list[str]) -> list[tuple]:
    # Одна строка = один объект OSM в одном домене.
    # Объект, участвующий в двух доменах (жилой дом), даёт две строки.
    # ST_Centroid превращает любую геометрию (точку, линию, полигон) в точку, а из точки берём lon/lat.
    # LEFT JOIN districts находит район, в который попала точка; если районов в БД нет, будет NULL.
    # Контур (GeoJSON) отдаём только для жилых домов: по нему считается площадь, остальным он не нужен.
    # Центроид и район считаются один раз на объект, а не на каждую пару (объект, домен):
    # у жилого дома две строки классификации, а поиск района самая дорогая часть запроса.
    placeholders = ", ".join("?" * len(domains))
    return con.execute(
        f"""
        WITH classified AS (
            SELECT * FROM osm_classification WHERE domain IN ({placeholders})
        ),
        objects AS (
            SELECT o.osm_type, o.osm_id, o.tags, o.geom, ST_Centroid(o.geom) AS pt
            FROM osm_objects o
            WHERE o.region = ?
              AND EXISTS (SELECT 1 FROM classified c
                          WHERE c.osm_type = o.osm_type AND c.osm_id = o.osm_id)
        ),
        located AS (
            SELECT ob.*, d.id AS district_id
            FROM objects ob
            LEFT JOIN districts d ON ST_Within(ob.pt, d.geom)
        )
        SELECT l.osm_type,
               l.osm_id,
               CAST(l.tags AS VARCHAR),
               ST_X(l.pt),
               ST_Y(l.pt),
               c.domain,
               c.role,
               c.kind,
               l.district_id,
               CASE WHEN c.kind = ? THEN CAST(ST_AsGeoJSON(l.geom) AS VARCHAR) END
        FROM located l
        JOIN classified c ON c.osm_type = l.osm_type AND c.osm_id = l.osm_id
        ORDER BY l.osm_type, l.osm_id, c.domain, l.district_id
        """,
        [*domains, region_id, RESIDENCE],
    ).fetchall()


def make_subject_id(osm_type: str, osm_id: int) -> str:
    # Id строится из id в OSM, поэтому при повторном запуске один и тот же объект
    # получает тот же id (например, node 123 -> s_n123)
    return f"s_{osm_type[0]}{osm_id}"


def make_address(tags: dict) -> str | None:
    street, house = tags.get("addr:street"), tags.get("addr:housenumber")
    if street and house:
        return f"{street}, {house}"
    return street or None


def footprint_area_m2(geometry: dict | None) -> float:
    # Площадь контура здания в м². Координаты в градусах, поэтому переводим их в метры:
    # градус широты везде одной длины, а градус долготы короче в cos(широты) раз.
    # У точки и линии площади нет, для них вернётся 0.
    if not geometry or geometry.get("type") not in ("Polygon", "MultiPolygon"):
        return 0.0
    polygon = shape(geometry)
    meters = scale(
        polygon,
        xfact=METERS_PER_DEGREE * math.cos(math.radians(polygon.centroid.y)),
        yfact=METERS_PER_DEGREE,
        origin=(0, 0),
    )
    return meters.area


def parse_levels(tags: dict) -> float:
    # Этажность из тега building:levels. В OSM встречается "5", "2,5", "5;6": берём первое число.
    # Если тега нет или в нём нет положительного числа, считаем дом одноэтажным.
    match = re.search(r"\d+(?:[.,]\d+)?", str(tags.get("building:levels", "")))
    if match:
        levels = float(match.group().replace(",", "."))
        if levels > 0:
            return levels
    return DEFAULT_LEVELS


def residence_capacity(tags: dict, geometry: dict | None) -> float | None:
    # Ёмкость жилого дома: площадь застройки * этажность. None, если площадь неизвестна.
    area = footprint_area_m2(geometry)
    return area * parse_levels(tags) if area > 0 else None


def build_subjects(rows: list[tuple]) -> list[Subject]:
    # Склеивает строки (объект, домен) в субъектов с списком ёмкостей.
    # Функция не обращается к БД, поэтому её легко проверять тестами.
    subjects: dict[str, Subject] = {}
    roles: dict[str, dict[str, str]] = {}      # id субъекта -> {домен: роль}
    own_capacity: dict[str, float | None] = {}  # жилой дом -> ёмкость по размерам (None, если не посчитать)

    for osm_type, osm_id, tags_json, lon, lat, domain, role, kind, district_id, geometry_json in rows:
        subject_id = make_subject_id(osm_type, osm_id)

        if subject_id not in subjects:  # первая строка объекта: создаём субъекта
            tags = json.loads(tags_json)
            subjects[subject_id] = Subject(
                id=subject_id,
                name=tags.get("name"),
                kind=kind,
                lon=lon,
                lat=lat,
                address=make_address(tags),
                district_id=district_id,
            )
            if kind == RESIDENCE:
                geometry = json.loads(geometry_json) if geometry_json else None
                own_capacity[subject_id] = residence_capacity(tags, geometry)

        if kind not in NO_CAPACITY_KINDS:
            # Если точка попала в несколько пересекающихся районов, SQL вернёт строку на каждый район.
            # Словарь хранит пару (домен -> роль) один раз: в БД она должна быть уникальной.
            roles.setdefault(subject_id, {})[domain] = role

    # Средняя ёмкость жилых домов, у которых удалось посчитать размеры
    measured = [value for value in own_capacity.values() if value]
    average = sum(measured) / len(measured) if measured else DEFAULT_CAPACITY

    for subject_id, subject in subjects.items():
        capacity = own_capacity.get(subject_id) or average  # дом без размеров и не-дома получают среднее
        subject.capacities = [
            Capacity(domain, role, capacity) for domain, role in sorted(roles.get(subject_id, {}).items())
        ]

    return list(subjects.values())


def main() -> None:
    cfg = get_config()
    domains = cfg.enabled_domains  # выключенные домены (goods) пропускаем

    with connect(cfg.paths.db, read_only=False) as con:
        init_schema(con)
        districts_count = con.execute("SELECT count(*) FROM districts").fetchone()[0]
        if districts_count == 0:
            print("Предупреждение: в таблице districts пусто, у всех субъектов не будет района. "
                  "Сначала загрузите границы районов.")
        rows = fetch_rows(con, cfg.region_id, domains)
        subjects = build_subjects(rows)
        Repository(con).save_subjects(subjects)

    capacities = sum(len(s.capacities) for s in subjects)
    without_district = sum(1 for s in subjects if s.district_id is None)
    print(f"Субъектов: {len(subjects)}, ёмкостей: {capacities}")
    if without_district:
        print(f"Без района: {without_district} (точка вне границ всех районов или районы не загружены)")


if __name__ == "__main__":
    main()