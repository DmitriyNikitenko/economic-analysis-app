# Чтение входных данных для метрик из DuckDB и запись результата в таблицу metrics
import duckdb

from backend.metrics.calculator import Edge, MetricRow, Node

class MetricsRepository:
    def __init__(self, con: duckdb.DuckDBPyConnection) -> None:
        self._con = con

    def load_nodes(self, domains: list[str]) -> list[Node]:
        # Узел = (субъект, домен) из capacities, район у субъекта
        if not domains:
            return []
        placeholders = ", ".join("?" * len(domains))
        rows = self._con.execute(
            "SELECT c.subject_id, c.domain, s.district_id "
            "FROM capacities c JOIN subjects s ON s.id = c.subject_id "
            f"WHERE c.domain IN ({placeholders}) "
            "ORDER BY c.domain, c.subject_id",
            domains,
        ).fetchall()
        return [Node(subject_id, domain, district_id) for subject_id, domain, district_id in rows]

    def load_edges(self, domains: list[str]) -> list[Edge]:
        if not domains:
            return []
        placeholders = ", ".join("?" * len(domains))
        rows = self._con.execute(
            f"SELECT domain, from_id, to_id FROM edges WHERE domain IN ({placeholders}) "
            "ORDER BY id",
            domains,
        ).fetchall()
        return [Edge(domain, from_id, to_id) for domain, from_id, to_id in rows]

    def load_districts(self) -> dict[str, str]:
        rows = self._con.execute("SELECT id, name FROM districts ORDER BY id").fetchall()
        return {district_id: name for district_id, name in rows}

    def replace_metrics(self, rows: list[MetricRow]) -> None:
        # Таблица пересоздаётся целиком: повторный запуск даёт тот же результат
        self._con.execute("BEGIN")
        try:
            self._con.execute("DELETE FROM metrics")
            if rows:
                self._con.executemany(
                    "INSERT INTO metrics "
                    "(scope, district_id, domain, node_count, edge_count, avg_degree, low_data) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [(r.scope, r.district_id, r.domain, r.node_count,
                      r.edge_count, r.avg_degree, r.low_data) for r in rows],
                )
            self._con.execute("COMMIT")
        except Exception:
            self._con.execute("ROLLBACK")
            raise

    def load_metrics(self) -> list[MetricRow]:
        rows = self._con.execute(
            "SELECT scope, district_id, domain, node_count, edge_count, avg_degree, low_data "
            "FROM metrics ORDER BY scope DESC, district_id, domain"
        ).fetchall()
        return [MetricRow(*row) for row in rows]