# Сборщик сущностей: превращает классифицированные объекты OSM в таблицу subjects и capacities
# loader -> classifier -> ingest -> entity_builder -> graph -> metrics -> export
#
# Как считается ёмкость (новая схема):
#   ёмкость = площадь * коэффициент типа (CAPACITY_SPECS);
#   площадь = контур * этажность, иначе типовая площадь типа;
#   жилой дом: площадь * этажность -> число жителей (m^2 / M2_PER_RESIDENT) или работников в домене labor;
#   после этого ёмкости не-домов в каждом домене масштабируются так, чтобы сумма предложения
#   совпала с суммой спроса: в OSM нет абсолютных мощностей банков и магазинов;
#   settlement  - справочный объект
import json
import math
import re
from dataclasses import dataclass
from shapely.affinity import scale
from shapely.geometry import shape
from backend.config import get_config
from backend.economy.db import connect, init_schema
from backend.economy.models import Capacity, Subject
from backend.economy.repository import Repository

RESIDENCE = "residence"
NO_CAPACITY_KINDS = {"settlement"} 
DEFAULT_AREA_M2 = 100.0
DEFAULT_LEVELS = 1
MAX_FOOTPRINT_M2 = 50_000

# Нормы для перевода площади в людей
M2_PER_RESIDENT = 30.0     # общей площади дома на одного жителя
WORKING_SHARE = 0.55       # доля трудоспособных среди жителей
M2_PER_JOB_OFFICE = 15.0   # m^2 офиса на одно рабочее место
M2_PER_JOB_INDUSTRY = 50.0 # m^2 производственного здания на одно рабочее место
M2_PER_JOB_LAND = 500.0    # m^2 промзоны на одно рабочее место

# Во сколько раз суммарное предложение домена больше суммарного спроса после балансировки
BALANCE_RATIO = 1.0
# Длина одного градуса дуги в метрах, как в backend/graph/engine.py
METERS_PER_DEGREE = 111_195

@dataclass(frozen=True)
class CapacitySpec:
    # Как считать ёмкость объекта этого типа
    weights: dict[str, float] 
    use_area: bool = True        
    default_area: float | None = None 

CAPACITY_SPECS: dict[str, CapacitySpec] = {
    RESIDENCE: CapacitySpec({"money": 1 / M2_PER_RESIDENT,                  # жителей
                             "labor": WORKING_SHARE / M2_PER_RESIDENT,      # трудоспособных
                             "goods": 1 / M2_PER_RESIDENT}),                # потребителей
    # деньги: предложение, в m^2 отделения
    "bank_branch": CapacitySpec({"money": 1.0}, default_area=300),
    "atm": CapacitySpec({"money": 1.0}, use_area=False, default_area=30),   #
    "microfinance": CapacitySpec({"money": 1.0}, default_area=40),
    "financial_office": CapacitySpec({"money": 1.0}, default_area=100),
    # труд: спрос, в рабочих местах
    "industrial_facility": CapacitySpec({"labor": 1 / M2_PER_JOB_INDUSTRY}, default_area=2000),
    "industrial_area": CapacitySpec({"labor": 1 / M2_PER_JOB_LAND}, default_area=20_000),
    "office_government": CapacitySpec({"labor": 1 / M2_PER_JOB_OFFICE}, default_area=300),
    "office_company": CapacitySpec({"labor": 1 / M2_PER_JOB_OFFICE}, default_area=150),
    "office_professional": CapacitySpec({"labor": 1 / M2_PER_JOB_OFFICE}, default_area=60),
    "office_nonprofit": CapacitySpec({"labor": 1 / M2_PER_JOB_OFFICE}, default_area=60),
    "office_other": CapacitySpec({"labor": 1 / M2_PER_JOB_OFFICE}, default_area=100),
    # товары и услуги: предложение, в m^2 торговой площади с поправкой на оборот
    "supermarket": CapacitySpec({"goods": 1.0}, default_area=1500),
    "shop_food": CapacitySpec({"goods": 1.5}, default_area=80),
    "shop_goods": CapacitySpec({"goods": 0.7}, default_area=80),
    "personal_service": CapacitySpec({"goods": 0.5}, default_area=40),
    "food_service": CapacitySpec({"goods": 1.0}, default_area=100),
}
DEFAULT_SPEC = CapacitySpec({}, use_area=False, default_area=DEFAULT_AREA_M2)
AREA_KINDS = tuple(sorted(kind for kind, spec in CAPACITY_SPECS.items() if spec.use_area))

def fetch_rows(con, region_id: str, domains: list[str]) -> list[tuple]:
    placeholders = ", ".join("?" * len(domains))
    area_placeholders = ", ".join("?" * len(AREA_KINDS))
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
               c.group_key,
               l.district_id,
               CASE WHEN c.kind IN ({area_placeholders}) THEN CAST(ST_AsGeoJSON(l.geom) AS VARCHAR) END
        FROM located l
        JOIN classified c ON c.osm_type = l.osm_type AND c.osm_id = l.osm_id
        ORDER BY l.osm_type, l.osm_id, c.domain, l.district_id
        """,
        [*domains, region_id, *AREA_KINDS],
    ).fetchall()


def make_subject_id(osm_type: str, osm_id: int) -> str:
    return f"s_{osm_type[0]}{osm_id}"


def make_address(tags: dict) -> str | None:
    street, house = tags.get("addr:street"), tags.get("addr:housenumber")
    if street and house:
        return f"{street}, {house}"
    return street or None


def footprint_area_m2(geometry: dict | None) -> float:
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
    match = re.search(r"\d+(?:[.,]\d+)?", str(tags.get("building:levels", "")))
    if match:
        levels = float(match.group().replace(",", "."))
        if levels > 0:
            return levels
    return DEFAULT_LEVELS


def residence_capacity(tags: dict, geometry: dict | None) -> float | None:
    area = min(footprint_area_m2(geometry), MAX_FOOTPRINT_M2)
    return area * parse_levels(tags) if area > 0 else None


def build_subjects(rows: list[tuple]) -> list[Subject]:
    subjects: dict[str, Subject] = {}
    roles: dict[str, dict[str, str]] = {} 
    own_area: dict[str, float | None] = {} 

    for osm_type, osm_id, tags_json, lon, lat, domain, role, kind, group_key, district_id, geometry_json in rows:
        subject_id = make_subject_id(osm_type, osm_id)

        if subject_id not in subjects:  # первая строка объекта: создаём субъекта
            tags = json.loads(tags_json)
            subjects[subject_id] = Subject(
                id=subject_id,
                name=tags.get("name"),
                kind=kind,
                group=group_key,
                lon=lon,
                lat=lat,
                address=make_address(tags),
                district_id=district_id,
            )
            if CAPACITY_SPECS.get(kind, DEFAULT_SPEC).use_area:
                geometry = json.loads(geometry_json) if geometry_json else None
                own_area[subject_id] = residence_capacity(tags, geometry)
        if kind not in NO_CAPACITY_KINDS:
            # Если точка попала в несколько пересекающихся районов, SQL вернёт строку на каждый район.
            # Словарь хранит пару (домен -> роль) один раз
            roles.setdefault(subject_id, {})[domain] = role

    # Средняя площадь жилых домов
    measured = [own_area[sid] for sid, s in subjects.items() if s.kind == RESIDENCE and own_area.get(sid)]
    average_house_area = sum(measured) / len(measured) if measured else DEFAULT_AREA_M2

    for subject_id, subject in subjects.items():
        spec = CAPACITY_SPECS.get(subject.kind, DEFAULT_SPEC)
        fallback = average_house_area if subject.kind == RESIDENCE else spec.default_area
        area = own_area.get(subject_id) or fallback or DEFAULT_AREA_M2
        subject.capacities = [
            Capacity(domain, role, area * spec.weights.get(domain, 1.0))
            for domain, role in sorted(roles.get(subject_id, {}).items())
        ]
    result = list(subjects.values())
    balance_capacities(result)
    return result


def balance_capacities(subjects: list[Subject]) -> None:
    houses: dict[str, float] = {}
    others: dict[str, float] = {}
    for subject in subjects:
        totals = houses if subject.kind == RESIDENCE else others
        for capacity in subject.capacities:
            totals[capacity.domain] = totals.get(capacity.domain, 0.0) + capacity.capacity

    factors = {domain: BALANCE_RATIO * houses[domain] / total
               for domain, total in others.items() if total > 0 and houses.get(domain)}
    for subject in subjects:
        if subject.kind == RESIDENCE:
            continue
        for capacity in subject.capacities:
            capacity.capacity *= factors.get(capacity.domain, 1.0)


def main() -> None:
    cfg = get_config()
    domains = cfg.enabled_domains

    with connect(cfg.paths.db, read_only=False) as con:
        init_schema(con)
        districts_count = con.execute("SELECT count(*) FROM districts").fetchone()[0]
        if districts_count == 0:
            print("Предупреждение: в таблице districts пусто, у всех субъектов не будет района. "
                  "Сначала загрузите границы районов.")
        rows = fetch_rows(con, cfg.region_id, domains)
        subjects = build_subjects(rows)
        Repository(con).save_subjects(subjects)

    unknown = {s.kind for s in subjects} - set(CAPACITY_SPECS) - NO_CAPACITY_KINDS
    if unknown:
        print(f"Предупреждение: для типов {sorted(unknown)} нет записи в CAPACITY_SPECS, "
              f"ёмкость посчитана по типовой площади {DEFAULT_AREA_M2:g} m^2. Добавьте их в таблицу.")

    capacities = sum(len(s.capacities) for s in subjects)
    without_district = sum(1 for s in subjects if s.district_id is None)
    print(f"Субъектов: {len(subjects)}, ёмкостей: {capacities}")
    if without_district:
        print(f"Без района: {without_district} (точка вне границ всех районов или районы не загружены)")


if __name__ == "__main__":
    main()