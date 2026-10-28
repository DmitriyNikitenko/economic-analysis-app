import json
from pathlib import Path
import pytest

from backend.economy.db import init_schema
from backend.economy.repository import OsmObjectRepository
from backend.export_gjs.exporter import export_osm_to_geojson


@pytest.fixture
def populated_db(monkeypatch):
    # Подменяем подключение к БД в экспортере на тестовую базу в памяти
    import duckdb
    con = duckdb.connect(":memory:")
    init_schema(con)

    # Заполняем тестовыми данными
    con.execute(
        "INSERT INTO osm_objects (osm_type, osm_id, tags, geom, region) "
        "VALUES ('node', 1, '{\"amenity\": \"bank\"}', ST_GeomFromGeoJSON('{\"type\": \"Point\", \"coordinates\": [39.9, 57.6]}'), 'yaroslavl')"
    )

    # Мокируем функцию connect в модуле exporter, чтобы она возвращала нашу тестовую базу
    monkeypatch.setattr("backend.export_gjs.exporter.connect", lambda read_only=True: con)
    return con


def test_export_creates_valid_geojson(populated_db, tmp_path):
    # Создаем временный файл для теста, чтобы не засорять реальную папку data/
    out_file = tmp_path / "test_output.geojson"

    # Запускаем экспорт
    export_osm_to_geojson(output_path=out_file)

    # Проверяем, что файл создался
    assert out_file.exists()

    # Читаем и проверяем структуру GeoJSON
    data = json.loads(out_file.read_text(encoding="utf-8"))

    assert data["type"] == "FeatureCollection"
    assert isinstance(data["features"], list)
    assert len(data["features"]) == 1

    feature = data["features"][0]
    assert feature["type"] == "Feature"
    assert feature["geometry"]["type"] == "Point"
    assert feature["properties"]["osm_id"] == 1
    assert feature["properties"]["tags"]["amenity"] == "bank"


def test_export_with_region_filter(populated_db, tmp_path):
    out_file = tmp_path / "filtered_output.geojson"

    # Передаем несуществующий регион
    export_osm_to_geojson(output_path=out_file, region="other_region")

    data = json.loads(out_file.read_text(encoding="utf-8"))
    # Объектов быть не должно
    assert len(data["features"]) == 0