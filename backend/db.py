import os
from functools import lru_cache

from dotenv import load_dotenv
from sqlalchemy import URL, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session


def database_url():
    load_dotenv()
    if os.getenv("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    if not os.getenv("PGPASSWORD"):
        raise RuntimeError("Configure DATABASE_URL o las variables PG* (ver .env.example)")
    return URL.create(
        "postgresql+psycopg", username=os.environ["PGUSER"],
        password=os.environ["PGPASSWORD"], host=os.getenv("PGHOST", "db"),
        port=int(os.getenv("PGPORT", "5432")), database=os.environ["PGDATABASE"],
    )


@lru_cache
def engine():
    return create_engine(database_url(), pool_pre_ping=True)


@lru_cache
def panel_engine():
    url = make_url(database_url())
    return create_engine(url.set(username=os.environ["DB_PANEL_USER"], password=os.environ["DB_PANEL_PASSWORD"]),
                         pool_pre_ping=True)


def get_session():
    with Session(panel_engine() if os.getenv("DB_PANEL_PASSWORD") else engine()) as session:
        # La dependencia es dueña de la transacción, incluso en errores HTTP.
        with session.begin():
            yield session
