"""Crea únicamente una base terminada en _test; nunca borra ni vacía bases."""
import os
from dotenv import load_dotenv
from psycopg import connect, sql
from sqlalchemy.engine import make_url
from backend.db import database_url


def main():
    load_dotenv()
    test = make_url(os.environ["TEST_DATABASE_URL"])
    source = make_url(str(database_url())) if isinstance(database_url(), str) else database_url()
    if not test.database or not test.database.endswith("_test") or test.database == source.database:
        raise SystemExit("TEST_DATABASE_URL debe apuntar a una base separada con sufijo _test")
    # Conectarse al mismo servidor que define TEST_DATABASE_URL.
    with connect(host=test.host, port=test.port, user=test.username, password=test.password,
                 dbname="postgres", autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname=%s", (test.database,)).fetchone()
        if not exists:
            conn.execute(sql.SQL("CREATE DATABASE {} WITH TEMPLATE template0").format(sql.Identifier(test.database)))
    print(f"Base de pruebas disponible: {test.database}")


if __name__ == "__main__":
    main()
