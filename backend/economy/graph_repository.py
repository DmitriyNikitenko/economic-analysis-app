# Чтение таблиц графа (subjects, capacities, edges, districts) из DuckDB
import json
import duckdb
from backend.economy.models import Capacity, District, Edge, Subject

def _in_clause(column: str, values: list[str]) -> str:
    # cтроит "column IN (?, ?)" под список значений
    return f"{column} IN ({', '.join('?' * len(values))})"


class GraphRepository:
    def __init__(self, con: duckdb.DuckDBPyConnection) -> None:
        self._con = con

    def get_subjects(self, domains: list[str] | None = None) -> list[Subject]:
        # cубъекты вместе с их ёмкостями по доменам
        params: list = []
        join_filter = ""
        if domains is not None:
            if not domains:
                return []
            join_filter = " AND " + _in_clause("c.domain", domains)
            params = list(domains)

        rows = self._con.execute(
            "SELECT s.id, s.name, s.kind, s.lon, s.lat, s.address, s.district_id, "
            "       c.domain, c.role, c.capacity "
            "FROM subjects s "
            f"LEFT JOIN capacities c ON c.subject_id = s.id{join_filter} "
            "ORDER BY s.id, c.domain",
            params,
        ).fetchall()

        subjects: dict[str, Subject] = {}
        for (subject_id, name, kind, lon, lat, address, district_id,
             domain, role, capacity) in rows:
            subject = subjects.get(subject_id)
            if subject is None:  # первая строка субъекта
                subject = Subject(subject_id, name, kind, lon, lat, address, district_id)
                subjects[subject_id] = subject
            if domain is not None:  # у субъекта без ёмкостей список остаётся пустым
                subject.capacities.append(Capacity(domain, role, capacity))

        result = list(subjects.values())
        if domains is not None:
            result = [s for s in result if s.capacities]
        return result

    def get_edges(self, domains: list[str] | None = None) -> list[Edge]:
        params: list = []
        where = ""
        if domains is not None:
            if not domains:
                return []
            where = " WHERE " + _in_clause("domain", domains)
            params = list(domains)

        rows = self._con.execute(
            f"SELECT id, domain, from_id, to_id, distance_km, weight FROM edges{where} ORDER BY id",
            params,
        ).fetchall()
        return [Edge(*row) for row in rows]

    def get_districts(self) -> list[District]:
        rows = self._con.execute(
            "SELECT id, name, ST_AsGeoJSON(geom) FROM districts ORDER BY id"
        ).fetchall()
        districts = []
        for district_id, name, geom in rows:
            if geom is None:  # район без границы нельзя нарисовать и проверить принадлежность узлов
                raise ValueError(f"У района {district_id} нет границы (geom)")
            districts.append(District(district_id, name, json.loads(geom)))
        return districts