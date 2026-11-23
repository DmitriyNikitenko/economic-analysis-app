import sys

from backend.config import get_config
from backend.economy.db import connect
from backend.economy.repository import Repository
from backend.graph.engine import build_gravity_edges
from backend.graph.equilibrium import build_equilibrium_edges
from backend.graph.updater import update_edges


def main() -> None:
    cfg = get_config()
    if not cfg.paths.db.exists():
        sys.exit(f"Database not found: {cfg.paths.db}")

    try:
        with connect(read_only=False) as con:
            repo = Repository(con)
            subjects = repo.get_subjects()

            model = cfg.graph.model if hasattr(cfg, "graph") else "huff"
            if model == "huff":
                edges = build_gravity_edges(subjects, cfg)
            elif model == "equilibrium":
                edges = build_equilibrium_edges(subjects, cfg)
            else:
                raise ValueError(f"Unknown graph model: {model}")

            update_edges(repo, edges, cfg.enabled_domains)
    except Exception as e:
        sys.exit(f"Error while building graph: {e}")

if __name__ == "__main__":
    main()