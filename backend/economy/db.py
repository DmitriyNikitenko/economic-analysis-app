# Подключение к DuckDB и создание таблиц
from pathlib import Path
import duckdb

from backend.config import get_config

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect(path: str | Path | None = None, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    # открываем базу и подключаем расширение spatial
    # path=None: путь берётся из config/region.yaml (paths.db)
    # ':memory:' даёт базу в памяти
    if path is None:
        path = get_config().paths.db
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path), read_only=read_only)
    con.execute("INSTALL spatial")  # скачивается один раз
    con.execute("LOAD spatial")
    return con


def init_schema(con: duckdb.DuckDBPyConnection) -> None:
    # создаём все таблицы
    # повторный запуск не создаёт их заново (IF NOT EXISTS)
    con.execute(SCHEMA_PATH.read_text(encoding="utf-8"))