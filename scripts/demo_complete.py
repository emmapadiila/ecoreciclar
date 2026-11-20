"""Aprueba reglas FICTICIAS y completa ambos cierres, solamente en una base _test."""
import os
from pathlib import Path
from decimal import Decimal
from dotenv import load_dotenv
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from alembic import command
from alembic.config import Config
from backend.models import ReglaPuntos, Solicitud, Usuario, CoordinadorColectivo
from backend.services import close_collection, set_actor


def main():
    load_dotenv()
    url = os.environ["TEST_DATABASE_URL"]
    if not make_url(url).database.endswith("_test") or url == os.getenv("DATABASE_URL"):
        raise SystemExit("Solo se permite una base separada _test")
    os.environ["DATABASE_URL"] = url
    command.upgrade(Config("alembic.ini"), "head")
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.exec_driver_sql(Path("database/seed_demo.sql").read_text(encoding="utf-8"))
    with Session(engine) as session, session.begin():
        admin = session.scalar(select(Usuario).where(Usuario.correo == "admin@example.invalid"))
        set_actor(session, admin.id)
        for rule in session.scalars(select(ReglaPuntos).where(~ReglaPuntos.aprobada)):
            rule.aprobada = True
            rule.aprobada_por = admin.id
        session.flush()
        for request in session.scalars(select(Solicitud).where(Solicitud.codigo.in_(["DEMO-ECO-REC", "DEMO-ECO-ORG"]))):
            if request.estado == "recolectada":
                print(request.codigo, "ya cerrada; no se duplica")
                continue
            coord_id = session.scalar(select(CoordinadorColectivo.usuario_id).where(
                CoordinadorColectivo.colectivo_id == request.colectivo_id, CoordinadorColectivo.activo))
            coordinator = session.get(Usuario, coord_id)
            collection, points = close_collection(session, coordinator, request.id, Decimal("5.00"))
            print(request.codigo, "peso", collection.peso_real_kg, "puntos ficticios", points)
    print("Ambos cierres confirmados en base de pruebas.")


if __name__ == "__main__":
    main()
