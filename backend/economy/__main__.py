import sys
from economy.db import DEFAULT_DB, connect, init_schema

def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "init-db":
        con = connect()
        init_schema(con)
        print(f"База создана: {DEFAULT_DB}")
    else:
        print("Команды: init-db")


if __name__ == "__main__":
    main()

# запуск: python -m economy init-db