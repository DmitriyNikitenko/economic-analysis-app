# Чтение объектов OSM и результатов классификации из DuckDB
import json
import duckdb
from backend.economy.models import DomainRole, OsmObject

_SELECT = """
    SELECT o.osm_type, o.osm_id,
           CAST(o.tags AS VARCHAR) AS tags,
           ST_AsGeoJSON(o.geom)    AS geometry,
           c.kind, c.domain, c.role, c.rule
    FROM osm_objects o
    LEFT JOIN osm_classification c USING (osm_type, osm_id)
"""
''' 
osm_objects o это исходные объекты
osm_classification c это результат классификации
USING (osm_type, osm_id) значит склеить строки у которых совпали тип и номер объекта
номер сам по себе не уникален, поэтому склейка идёт по паре
CAST(o.tags AS VARCHAR) превращает JSON-теги в обычную строку
ST_AsGeoJSON(o.geom) превращает внутреннюю геометрию DuckDB в текст GeoJSON
LEFT JOIN значит берём все объекты из левой таблицы, если для них нет строк классификации то подставляем NULL
'''

_ORDER = " ORDER BY o.osm_type, o.osm_id, c.domain"


class OsmObjectRepository:
    def __init__(self, con: duckdb.DuckDBPyConnection) -> None:
        self._con = con

    def find_all(self) -> list[OsmObject]:
        return self._read(_SELECT + _ORDER, [])

    def find_by_region(self, region: str) -> list[OsmObject]:
        return self._read(_SELECT + " WHERE o.region = ?" + _ORDER, [region])

    def _read(self, sql: str, params: list) -> list[OsmObject]:
        rows = self._con.execute(sql, params).fetchall() # получаем все сроки как список кортежей
        objects: dict[tuple[str, int], OsmObject] = {}
        for osm_type, osm_id, tags, geometry, kind, domain, role, rule in rows:
            key = (osm_type, osm_id)
            obj = objects.get(key)
            if obj is None:  # первая строка объекта
                # если такого ключа еще нет, создаем OsmObject
                obj = OsmObject(osm_type, osm_id, json.loads(tags), json.loads(geometry), kind)
                objects[key] = obj
            if domain is not None:  # у объекта без классификации ролей нет, список остается пустым
                obj.roles.append(DomainRole(domain, role, rule))
        return list(objects.values())