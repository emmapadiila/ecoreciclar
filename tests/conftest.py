import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from backend.auth import issue_token
from backend.db import engine as app_engine
from backend.main import app
from backend.models import Base, Usuario


@pytest.fixture(scope="session")
def database():
    load_dotenv()
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.fail("Configure TEST_DATABASE_URL: estas pruebas requieren PostgreSQL real")
    parsed = make_url(url)
    original = os.getenv("DATABASE_URL", "")
    if not parsed.database or not parsed.database.endswith("_test"):
        pytest.fail("Las pruebas solo pueden vaciar una base cuyo nombre termine en _test")
    if original and parsed.database == make_url(original).database:
        pytest.fail("Las pruebas no pueden usar la misma base que DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    app_engine.cache_clear()
    command.upgrade(Config("alembic.ini"), "head")
    engine = create_engine(url, pool_pre_ping=True)
    yield engine
    engine.dispose()
    app_engine().dispose()
    app_engine.cache_clear()
    if original:
        os.environ["DATABASE_URL"] = original
    else:
        os.environ.pop("DATABASE_URL", None)


@pytest.fixture(autouse=True)
def clean_database(database, monkeypatch):
    monkeypatch.setenv("WHATSAPP_PROVIDER", "meta")
    monkeypatch.setenv("DB_PANEL_PASSWORD", "")
    tables = ", ".join('"' + table.name + '"' for table in Base.metadata.sorted_tables)
    with database.begin() as connection:
        connection.exec_driver_sql(f"TRUNCATE {tables} RESTART IDENTITY CASCADE")
        connection.exec_driver_sql(Path("database/seed_demo.sql").read_text(encoding="utf-8"))
    yield
    with database.begin() as connection:
        connection.exec_driver_sql(f"TRUNCATE {tables} RESTART IDENTITY CASCADE")


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


@pytest.fixture
def headers(database):
    with Session(database) as session:
        return {user.correo: {"Authorization": "Bearer " + issue_token(user.id)}
                for user in session.scalars(select(Usuario))}
