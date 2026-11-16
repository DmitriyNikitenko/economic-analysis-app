import sys

from backend.config import get_config
from backend.economy.db import connect
from backend.economy.repository import Repository
from backend.graph.engine import build_gravity_edges
from backend.graph.updater import update_edges


def main() -> None:
    cfg = get_config()
    if not cfg.paths.db.exists():
        sys.exit(f"Database not found: {cfg.paths.db}")

    try:
        with connect(read_only=False) as con:
            repo = Repository(con)
            subjects = repo.get_subjects()
            edges = build_gravity_edges(subjects, cfg)
            update_edges(repo, edges, cfg.enabled_domains)
    except Exception as e:
        sys.exit(f"Error while building graph: {e}")

if __name__ == "__main__":
    main()