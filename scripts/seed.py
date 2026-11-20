from pathlib import Path
from backend.db import engine


def main():
    with engine().begin() as conn:
        conn.exec_driver_sql(Path("database/seed_demo.sql").read_text(encoding="utf-8"))
    print("Seed DEMO aplicado. Dos solicitudes programadas; reglas sin aprobar, sin puntos.")


if __name__ == "__main__":
    main()
