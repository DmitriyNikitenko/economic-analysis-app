import sys

from backend.config import get_config
from backend.economy.db import connect
from backend.economy.repository import Repository
from backend.export_gjs.export import run_export


def main() -> None:
    cfg = get_config()

    if not cfg.paths.db.exists():
        sys.exit(1)

    try:
        with connect(read_only=True) as con:
            repo = Repository(con)
            run_export(repo, output_dir=cfg.paths.frontend_data)
    except Exception as e:
        sys.exit(2)


if __name__ == "__main__":
    main()