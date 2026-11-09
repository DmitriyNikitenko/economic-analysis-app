import sys

from backend.config import get_config
from backend.economy.db import connect, init_schema


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "init-db":
        con = connect()
        init_schema(con)
        print(f"База создана: {get_config().paths.db}")
    else:
        print("Команды: init-db")


if __name__ == "__main__":
    main()

# запуск из корня репозитория: python -m backend.economy init-db