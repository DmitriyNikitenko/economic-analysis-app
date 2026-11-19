# общие фикстуры: чистая бд в памяти и репозиторий поверх неё
import duckdb
import pytest

from backend.economy.db import connect, init_schema
from backend.economy.repository import Repository


@pytest.fixture
def con():
    try:
        con = connect(":memory:")
    except duckdb.Error as e:
        pytest.skip(f"расширение spatial недоступно: {e}")
    init_schema(con)
    yield con
    con.close()

@pytest.fixture
def repo(con):
    return Repository(con)