# Подключение к DuckDB и создание таблиц
from pathlib import Path
import duckdb

DEFAULT_DB = Path("data/region.duckdb")
SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect(path: str | Path = DEFAULT_DB, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    # открываем базу и подключаем расширение spatial
    # ':memory:' даёт базу в памяти
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path), read_only=read_only)
    con.execute("INSTALL spatial")  # скачивается один раз
    con.execute("LOAD spatial")
    return con


def init_schema(con: duckdb.DuckDBPyConnection) -> None:
    # создаём все таблицы
    # повторный запуск не создает заново
    con.execute(SCHEMA_PATH.read_text(encoding="utf-8"))