import argparse
import os
from pathlib import Path

from backend.config import get_config
from backend.loader.pbf_loader import load_pbf
from backend.loader.osm_loader import get_data, get_districts
from backend.loader.pbf_loader import write_json
from backend.classification.classifier import classify_data
from backend.ingest.__main__ import ingest

from backend.economy.db import connect, init_schema
from backend.economy.repository import Repository

from backend.entity_builder.__main__ import fetch_rows, build_subjects
from backend.graph.road_graph import build_road_graph
from backend.graph.engine import build_gravity_edges
from backend.graph.equilibrium import build_equilibrium_edges
from backend.graph.updater import update_edges
from backend.metrics.calculator import compute_metrics
from backend.export_gjs.exporter import run_export

ROOT = Path(__file__).resolve().parents[1]

def _relative(path: Path) -> Path:
    """Путь относительно текущей папки"""
    try:
        return Path(os.path.relpath(path, Path.cwd()))
    except ValueError:
        return path
    
def find_pbf() -> Path:
    """Находит единственный PBF-файл в data/pbf."""
    pbf_dir = ROOT / "data" / "pbf"

    if not pbf_dir.exists():
        raise FileNotFoundError(
            f"Папка с PBF-файлами не найдена: {pbf_dir}"
        )

    files = sorted(pbf_dir.glob("*.pbf"))

    if not files:
        raise FileNotFoundError(
            f"В папке {pbf_dir} нет PBF-файлов."
        )

    if len(files) > 1:
        names = "\n".join(f"  - {path.name}" for path in files)
        raise ValueError(
            "Найдено несколько PBF-файлов. "
            "Укажите нужный через --pbf:\n" + names
        )

    return _relative(files[0])

def save_geojson(data: dict, path: Path) -> Path:
    """Сохраняет GeoJSON в файл."""
    return write_json(data, path)

def load_source(args, cfg):
    """Загружает исходные объекты и районы."""
    if args.source == "pbf":
        pbf_path = args.pbf if args.pbf else find_pbf()

        print(f"Источник: PBF ({pbf_path})")

        raw_data, districts_data, stats = load_pbf(
            pbf_path=pbf_path,
            region=cfg.region_id,
            region_name=cfg.region_name.split(",")[0].strip()
        )

        return raw_data, districts_data

    print("Источник: Overpass API")

    raw_data = get_data(
        region=cfg.region_id,
    )

    districts_data = get_districts(
        region=cfg.region_id,
    )

    print(f"Загружено объектов: {len(raw_data['features'])}")
    print(f"Загружено районов: {len(districts_data['features'])}")

    return raw_data, districts_data

def build_entities(cfg):
    """Создаёт субъектов и ёмкости."""
    domains = cfg.enabled_domains

    if not domains:
        raise ValueError(
            "Не включён ни один экономический домен."
        )

    with connect(cfg.paths.db, read_only=False) as con:
        init_schema(con)

        districts_count = con.execute(
            "SELECT count(*) FROM districts"
        ).fetchone()[0]

        if districts_count == 0:
            print(
                "Предупреждение: таблица districts пуста. "
                "У субъектов не будет районов."
            )

        rows = fetch_rows(
            con,
            cfg.region_id,
            domains,
        )

        subjects = build_subjects(rows)
        Repository(con).save_subjects(subjects)

    capacities = sum(
        len(subject.capacities)
        for subject in subjects
    )

    print(
        f"Субъектов: {len(subjects)}, "
        f"ёмкостей: {capacities}"
    )

    return subjects

def build_graph(cfg):
    """Строит экономический граф и сохраняет связи."""
    with connect(cfg.paths.db, read_only=False) as con:
        repo = Repository(con)
        subjects = repo.get_subjects()

        model = cfg.graph.model

        if model == "huff":
            edges = build_gravity_edges(subjects, cfg)
        elif model == "equilibrium":
            edges = build_equilibrium_edges(subjects, cfg)
        else:
            raise ValueError(
                f"Неизвестная модель графа: {model}"
            )

        update_edges(
            repo,
            edges,
            cfg.enabled_domains,
        )

    print(f"Построение графа завершено. Связей: {len(edges)}")

def calculate_metrics(cfg):
    """Рассчитывает и сохраняет метрики."""
    domains = cfg.enabled_domains

    with connect(cfg.paths.db, read_only=False) as con:
        init_schema(con)
        repo = Repository(con)

        metrics = compute_metrics(
            subjects=repo.get_subjects(domains),
            edges=repo.get_edges(domains),
            district_ids=[
                district.id
                for district in repo.get_districts()
            ],
            domains=domains,
            low_data_threshold=cfg.low_data_threshold,
        )

        repo.save_metrics(metrics)

    print(f"Рассчитано метрик: {len(metrics)}")

def export_frontend(cfg):
    """Экспортирует итоговые данные для frontend."""
    with connect(cfg.paths.db, read_only=True) as con:
        repo = Repository(con)

        run_export(
            repo,
            output_dir=cfg.paths.frontend_data,
            enabled_domains=cfg.enabled_domains,
        )

    print(f"Данные frontend сохранены: {cfg.paths.frontend_data}")

def run_pipeline(args):
    cfg = get_config()

    print("=" * 55)
    print("ЗАПУСК PIPELINE")
    print(f"Регион: {cfg.region_name}")
    print(f"Домены: {', '.join(cfg.enabled_domains)}")
    print("=" * 55)

    # 1. Загрузка
    print("\n[1/8] Загрузка исходных данных...")
    raw_data, districts_data = load_source(args, cfg)

    if not raw_data.get("features"):
        raise ValueError(
            "Загрузчик не вернул ни одного объекта. "
            "Дальнейшая обработка невозможна."
        )

    print(f"Исходных объектов: {len(raw_data['features'])}")
    print(f"Районов: {len(districts_data['features'])}")

    # 2. Классификация
    print("\n[2/8] Классификация объектов...")
    classified_data = classify_data(data=raw_data)

    print(
        f"Классифицировано объектов: "
        f"{len(classified_data['features'])}"
    )

    # Промежуточное сохранение по запросу
    if args.save:
        print("\nСохранение промежуточных файлов...")

        raw_path = save_geojson(
            raw_data,
            cfg.paths.raw,
        )

        classified_path = save_geojson(
            classified_data,
            cfg.paths.classified,
        )

        districts_path = save_geojson(
            districts_data,
            cfg.paths.districts,
        )

        print(f"Исходные данные: {raw_path}")
        print(f"Классификация: {classified_path}")
        print(f"Районы: {districts_path}")

    # 3. Загрузка в DuckDB
    print("\n[3/8] Загрузка данных в DuckDB...")

    ingest_result = ingest(
        data=classified_data,
        districts_data=districts_data,
        db_path=cfg.paths.db,
    )

    print(f"Записано объектов: {ingest_result['objects']}")
    print(
        f"Записей классификации: "
        f"{ingest_result['classifications']}"
    )
    print(
        f"Неклассифицированных объектов: "
        f"{ingest_result['unclassified']}"
    )
    print(
        f"Записано районов: "
        f"{ingest_result['districts']}"
    )

    # 4. Построение субъектов
    print("\n[4/8] Построение субъектов и ёмкостей...")
    build_entities(cfg)

    # 5. Загрузка дорожного графа
    print("\n[5/8] Загрузка дорожного графа...")
    build_road_graph()

    # 6. Построение графа
    print("\n[6/8] Построение экономического графа...")
    build_graph(cfg)

    # 7. Расчёт метрик
    print("\n[7/8] Расчёт метрик...")
    calculate_metrics(cfg)

    # 8. Экспорт
    print("\n[8/8] Экспорт данных для frontend...")
    export_frontend(cfg)

    print("\n" + "=" * 55)
    print("PIPELINE УСПЕШНО ЗАВЕРШЁН")
    print("=" * 55)


def main():
    parser = argparse.ArgumentParser(
        description="Полный цикл анализа экономической активности региона"
    )

    parser.add_argument(
        "--source",
        choices=("pbf", "overpass"),
        default="pbf",
        help="Источник OSM-данных (по умолчанию pbf).",
    )

    parser.add_argument(
        "--pbf",
        type=Path,
        default=None,
        help="Путь к PBF-файлу. Если не указан, ищется файл в data/pbf.",
    )

    parser.add_argument(
        "--save",
        action="store_true",
        help="Сохранить промежуточные GeoJSON-файлы.",
    )

    args = parser.parse_args()

    try:
        run_pipeline(args)
    except Exception as error:
        print(f"\nОШИБКА PIPELINE: {error}")
        raise


if __name__ == "__main__":
    main()
