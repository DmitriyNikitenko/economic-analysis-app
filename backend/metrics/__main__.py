from backend.config import get_config
from backend.economy.db import connect, init_schema
from backend.economy.repository import Repository
from backend.metrics.calculator import compute_metrics

def main() -> None:
    cfg = get_config()
    domains = cfg.enabled_domains

    con = connect(cfg.paths.db)
    init_schema(con)
    repo = Repository(con)

    metrics = compute_metrics(
        subjects=repo.get_subjects(domains),
        edges=repo.get_edges(domains),
        district_ids=[d.id for d in repo.get_districts()],
        domains=domains,
        low_data_threshold=cfg.low_data_threshold,
    )
    repo.save_metrics(metrics)
    print(f"Метрики посчитаны и сохранены в БД: {len(metrics)} строк")


if __name__ == "__main__":
    main()