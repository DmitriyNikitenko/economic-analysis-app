# Сборщик сущностей: превращает классифицированные объекты OSM в таблицу subjects и capacities
# loader -> classifier -> ingest -> entity_builder -> graph -> metrics -> export
# Запуск из корня репозитория:  python -m backend.entity_builder
import json

from backend.config import get_config
from backend.economy.db import connect, init_schema
from backend.economy.models import Capacity, Subject
from backend.economy.repository import Repository

# Ёмкость, если по данным OSM её не определить. Схема требует capacity > 0.
DEFAULT_CAPACITY = 1.0 # заглушка


def fetch_rows(con, region_id: str, domains: list[str]) -> list[tuple]:
    # Одна строка = один объект OSM в одном домене.
    # Объект, участвующий в двух доменах (населённый пункт), даёт две строки.
    # ST_Centroid превращает любую геометрию (точку, линию, полигон) в точку, а из точки берём lon/lat.
    # LEFT JOIN districts находит район, в который попала точка; если районов в БД нет, будет NULL.
    placeholders = ", ".join("?" * len(domains))
    return con.execute(
        f"""
        SELECT o.osm_type,
               o.osm_id,
               CAST(o.tags AS VARCHAR),
               ST_X(ST_Centroid(o.geom)),
               ST_Y(ST_Centroid(o.geom)),
               c.domain,
               c.role,
               c.kind,
               d.id
        FROM osm_objects o
        JOIN osm_classification c
          ON c.osm_type = o.osm_type AND c.osm_id = o.osm_id
        LEFT JOIN districts d
          ON ST_Within(ST_Centroid(o.geom), d.geom)
        WHERE o.region = ? AND c.domain IN ({placeholders})
        ORDER BY o.osm_type, o.osm_id, c.domain, d.id
        """,
        [region_id, *domains],
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


def estimate_capacity(kind: str, tags: dict) -> float:
    # Население населённого пункта берём из тега population, если он есть и это число.
    # Для банков и работодателей источника ёмкости пока нет, остаётся значение по умолчанию.
    if kind == "settlement":
        try:
            population = float(tags.get("population", ""))
        except ValueError:
            return DEFAULT_CAPACITY
        if population > 0:
            return population
    return DEFAULT_CAPACITY


def build_subjects(rows: list[tuple]) -> list[Subject]:
    # Склеивает строки (объект, домен) в субъектов с списком ёмкостей.
    # Функция не обращается к БД, поэтому её легко проверять тестами.
    subjects: dict[str, Subject] = {}

    for osm_type, osm_id, tags_json, lon, lat, domain, role, kind, district_id in rows:
        subject_id = make_subject_id(osm_type, osm_id)
        tags = json.loads(tags_json)

        subject = subjects.get(subject_id)
        if subject is None:  # первая строка объекта: создаём субъекта
            subject = Subject(
                id=subject_id,
                name=tags.get("name"),
                kind=kind,
                lon=lon,
                lat=lat,
                address=make_address(tags),
                district_id=district_id,
            )
            subjects[subject_id] = subject

        if all(c.domain != domain for c in subject.capacities):
            subject.capacities.append(Capacity(domain, role, estimate_capacity(kind, tags)))

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