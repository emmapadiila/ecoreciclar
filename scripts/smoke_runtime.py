"""Prueba ASGI contra PostgreSQL con rol limitado. Solo crea solicitudes DEMO en _test.

Requiere demo_complete y provision_runtime --test previos. No simula envío Meta.
"""
import os
from datetime import datetime, timedelta, timezone
from time import sleep
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from backend.auth import issue_token
from backend.db import engine
from backend.main import app
from backend.models import Colectivo, Material, Recolector, Usuario


def main():
    load_dotenv()
    url = make_url(os.environ["TEST_DATABASE_URL"])
    if not url.database.endswith("_test"):
        raise SystemExit("Solo ejecutar en base _test")
    url = url.set(username=os.environ["DB_APP_USER"], password=os.environ["DB_APP_PASSWORD"])
    os.environ["DATABASE_URL"] = url.render_as_string(hide_password=False)
    with engine().connect() as connection:
        role = connection.execute(text("SELECT current_user, rolsuper, rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname=current_user")).one()
        assert not any(role[1:]), "No probar con un rol privilegiado"
        assert not connection.scalar(text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')"))
        assert not connection.scalar(text("SELECT has_table_privilege(current_user, 'usuarios', 'TRUNCATE')"))
        assert not connection.scalar(text("SELECT has_column_privilege(current_user, 'usuarios', 'piloto_habilitado', 'UPDATE')"))
        assert not connection.scalar(text("SELECT has_column_privilege(current_user, 'reglas_puntos', 'aprobada', 'UPDATE')"))
        print("Rol limitado:", role[0], "sin superusuario, DDL, TRUNCATE ni aprobación de piloto/reglas")
    with TestClient(app) as client:
        for flow, suffix, expected in [("reciclable", "reciclaje", "50.00"), ("organico", "huerta", "25.00")]:
            with Session(engine()) as session:
                user = session.scalar(select(Usuario).where(Usuario.correo == f"residente.{suffix}@example.invalid"))
                coord = session.scalar(select(Usuario).where(Usuario.correo == f"coordinador.{suffix}@example.invalid"))
                cid = session.scalar(select(Colectivo.id).where(Colectivo.tipo_flujo == flow))
                mid = session.scalar(select(Material.id).where(Material.categoria == flow, Material.aceptado))
                rid = session.scalar(select(Recolector.id).where(Recolector.colectivo_id == cid))
                resident = {"Authorization": "Bearer " + issue_token(user.id)}
                coordinator = {"Authorization": "Bearer " + issue_token(coord.id)}
            response = client.post("/solicitudes", headers=resident, json={"direccion": "DEMO smoke runtime", "materiales": [{"material_id": mid, "confirmado": True}]})
            assert response.status_code == 201, response.text
            sid = response.json()["id"]
            response = client.post(f"/solicitudes/{sid}/asignacion", headers=coordinator, json={"recolector_id": rid})
            assert response.status_code == 201, response.text
            planned = datetime.now(timezone.utc) + timedelta(seconds=3)
            for step, payload in (("confirmacion", {"respuesta": "aceptacion"}),
                                  ("programacion", {"programada_en": planned.isoformat()}),
                                  ("recogida", {"fecha_real": planned.isoformat(), "resultado": "realizada"}),
                                  ("recepcion", {"fecha_real": planned.isoformat(), "material": "DEMO material"}),
                                  ("pesaje", {"peso_real_kg": "5", "material": "DEMO material"})):
                if step == "recogida":
                    sleep(max(0, (planned - datetime.now(timezone.utc)).total_seconds()))
                response = client.post(f"/solicitudes/{sid}/{step}", headers=coordinator, json=payload)
                assert response.status_code == 200, response.text
            response = client.post(f"/solicitudes/{sid}/cierre", headers=coordinator, json={"peso_real_kg": "5"})
            assert response.status_code == 200, response.text
            assert response.json()["puntos"] == expected
            print("PASS:", flow, "creación/asignación/programación/cierre/puntos con rol runtime")


if __name__ == "__main__":
    main()
