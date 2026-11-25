# Чтение и запись таблиц БД (subjects, capacities, edges, districts, metrics) в DuckDB
import json
from contextlib import contextmanager
import duckdb
import pandas as pd
from backend.economy.models import Capacity, District, Edge, Metric, Subject


def _in_clause(column: str, values: list[str]) -> str:
    # Строит "column IN (?, ?)" под список значений
    return f"{column} IN ({', '.join('?' * len(values))})"


class Repository:
    def __init__(self, con: duckdb.DuckDBPyConnection) -> None:
        self._con = con
        self._in_transaction = False

    @contextmanager
    def _transaction(self):
        if self._in_transaction:  # вложенный вызов: внешняя транзакция уже открыта
            yield
            return
        self._con.execute("BEGIN")
        self._in_transaction = True
        try:
            yield
            self._con.execute("COMMIT")
        except Exception:
            self._con.execute("ROLLBACK")
            raise
        finally:
            self._in_transaction = False

    def transaction(self):
        # Несколько операций одной транзакцией: with repo.transaction(): ...
        return self._transaction()
    
    def _insert_many(self, sql: str, rows: list[tuple]) -> None:
        if rows:
            self._con.executemany(sql, rows)

    def _insert_bulk(self, table: str, columns: list[str], rows: list[tuple]) -> None:
        # Для больших таблиц вся пачка одним запросом через DataFrame
        if not rows:
            return
        batch = pd.DataFrame(rows, columns=columns, dtype=object)
        self._con.register("_batch", batch)
        try:
            self._con.execute(f"INSERT INTO {table} ({', '.join(columns)}) SELECT * FROM _batch")
        finally:
            self._con.unregister("_batch")

    # ---------- subjects и capacities ----------
    def get_subjects(self, domains: list[str] | None = None) -> list[Subject]:
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

    def save_subjects(self, subjects: list[Subject]) -> None:
        # Таблицы subjects и capacities пересоздаются целиком
        with self._transaction():
            self._con.execute("DELETE FROM capacities")
            self._con.execute("DELETE FROM subjects")
            self._insert_bulk(
                "subjects",
                ["id", "name", "kind", "lon", "lat", "address", "district_id"],
                [(s.id, s.name, s.kind, s.lon, s.lat, s.address, s.district_id) for s in subjects],
            )
            self._insert_bulk(
                "capacities",
                ["subject_id", "domain", "role", "capacity"],
                [(s.id, c.domain, c.role, c.capacity) for s in subjects for c in s.capacities],
            )

    # ---------- edges ----------
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

    def _insert_edges(self, edges: list[Edge]) -> None:
        # вставка без транзакции: вызывается внутри транзакций методов ниже
        self._insert_bulk(
            "edges",
            ["id", "domain", "from_id", "to_id", "distance_km", "weight"],
            [(e.id, e.domain, e.from_id, e.to_id, e.distance_km, e.weight) for e in edges],
        )

    def save_edges(self, edges: list[Edge]) -> None:
        with self._transaction():
            self._con.execute("DELETE FROM edges")
            self._insert_edges(edges)

    def insert_edges(self, edges: list[Edge]) -> None:
        # добавляет рёбра к уже существующим, ничего не удаляя
        with self._transaction():
            self._insert_edges(edges)

    def delete_edges_by_domain(self, domain: str) -> None:
        # удаляет рёбра одного домена, рёбра других доменов остаются
        self._con.execute("DELETE FROM edges WHERE domain = ?", [domain])

    # ---------- districts ----------
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

    def save_districts(self, districts: list[District]) -> None:
        with self._transaction():
            self._con.execute("DELETE FROM districts")
            self._insert_many(
                "INSERT INTO districts (id, name, geom) VALUES (?, ?, ST_GeomFromGeoJSON(?))",
                [(d.id, d.name, json.dumps(d.geom)) for d in districts],
            )

    # ---------- metrics ----------
    def get_metrics(self) -> list[Metric]:
        rows = self._con.execute(
            "SELECT scope, district_id, domain, node_count, edge_count, avg_degree, low_data "
            "FROM metrics ORDER BY scope DESC, district_id, domain"
        ).fetchall()
        return [Metric(*row) for row in rows]

    def save_metrics(self, metrics: list[Metric]) -> None:
        with self._transaction():
            self._con.execute("DELETE FROM metrics")
            self._insert_many(
                "INSERT INTO metrics "
                "(scope, district_id, domain, node_count, edge_count, avg_degree, low_data) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                [(m.scope, m.district_id, m.domain, m.node_count,
                  m.edge_count, m.avg_degree, m.low_data) for m in metrics],
            )