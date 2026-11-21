"""Permisos de los perfiles registrados; la demostración no concede acceso API."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.auth import hash_password
from backend.models import Colectivo, CoordinadorColectivo, Material, Solicitud, Usuario


@pytest.mark.parametrize("email,role,flow", [
    ("admin@example.invalid", "administrador", None),
    ("coordinador.reciclaje@example.invalid", "coordinador", "reciclable"),
    ("coordinador.huerta@example.invalid", "coordinador", "organico"),
    ("residente.reciclaje@example.invalid", "residente", None),
])
def test_registered_login_uses_database_role(database, client, email, role, flow):
    with Session(database) as session, session.begin():
        user = session.scalar(select(Usuario).where(Usuario.correo == email))
        user.password_hash = hash_password("DEMO-role-test-password")
    response = client.post("/auth/token", json={"correo": email, "password": "DEMO-role-test-password"})
    assert response.status_code == 200
    auth = {"Authorization": "Bearer " + response.json()["access_token"]}
    profile = client.get("/auth/me", headers=auth)
    assert profile.status_code == 200
    assert profile.json()["rol"] == role
    assert profile.json()["colectivo_tipo"] == flow
    assert "password_hash" not in profile.json()
    assert client.post("/auth/token", json={
        "correo": email, "password": "DEMO-role-test-password", "rol": "administrador",
    }).status_code == 422


@pytest.mark.parametrize("role", ["administrador", "coordinador", "recolector"])
def test_only_resident_can_create_requests(database, client, headers, role):
    email = "admin@example.invalid"
    with Session(database) as session, session.begin():
        user = session.scalar(select(Usuario).where(Usuario.correo == email))
        user.rol = role
        material_id = session.scalar(select(Material.id).where(Material.aceptado))
    response = client.post("/solicitudes", headers=headers[email], json={
        "direccion": "DEMO", "materiales": [{"material_id": material_id, "confirmado": True}],
    })
    assert response.status_code == 403


@pytest.mark.parametrize("email", ["admin@example.invalid", "residente.reciclaje@example.invalid"])
def test_operational_writes_require_coordinator(database, client, headers, email):
    with Session(database) as session:
        sid = session.scalar(select(Solicitud.id).where(Solicitud.codigo == "DEMO-ECO-REC"))
    now = datetime.now(timezone.utc)
    payloads = {
        "estado": {"estado": "cancelada", "observacion": "DEMO"},
        "asignacion": {"recolector_id": 1},
        "confirmacion": {"respuesta": "aceptacion"},
        "programacion": {"programada_en": (now + timedelta(days=1)).isoformat()},
        "recogida": {"fecha_real": now.isoformat(), "resultado": "realizada"},
        "recepcion": {"fecha_real": now.isoformat(), "material": "DEMO"},
        "pesaje": {"peso_real_kg": "5", "material": "DEMO"},
        "cierre": {},
    }
    for action, payload in payloads.items():
        response = client.post(f"/solicitudes/{sid}/{action}", headers=headers[email], json=payload)
        assert response.status_code == 403, action


def test_admin_supervision_does_not_expose_operational_data(database, client, headers):
    auth = headers["admin@example.invalid"]
    with Session(database) as session:
        sid = session.scalar(select(Solicitud.id))
    for path in ("/solicitudes", f"/solicitudes/{sid}", f"/solicitudes/{sid}/historial", "/recolectores"):
        assert client.get(path, headers=auth).status_code == 403
    response = client.get("/public/resultados-diarios", headers=auth)
    assert response.status_code == 200
    assert set(response.json()) == {
        "fecha", "total_kg", "reciclables_kg", "organicos_kg", "recolecciones_confirmadas",
        "hogares_participantes", "negocios_participantes", "ultima_actualizacion",
    }


@pytest.mark.parametrize("disabled", ["membership", "collective"])
def test_coordinator_loses_scope_when_assignment_disabled(database, client, headers, disabled):
    email = "coordinador.reciclaje@example.invalid"
    auth = headers[email]
    sid = client.get("/solicitudes", headers=auth).json()[0]["id"]
    with Session(database) as session, session.begin():
        user = session.scalar(select(Usuario).where(Usuario.correo == email))
        membership = session.scalar(select(CoordinadorColectivo).where(CoordinadorColectivo.usuario_id == user.id))
        if disabled == "membership":
            membership.activo = False
        else:
            session.get(Colectivo, membership.colectivo_id).activo = False
    assert client.get("/solicitudes", headers=auth).json() == []
    assert client.get("/recolectores", headers=auth).json() == []
    assert client.get("/auth/me", headers=auth).json()["colectivo_tipo"] is None
    assert client.get(f"/solicitudes/{sid}", headers=auth).status_code == 404


def test_public_registration_persists_resident(database, client):
    response = client.post("/auth/register", json={
        "nombre": "Residente Nuevo",
        "correo": "nuevo@example.invalid",
        "password": "ClaveSegura123",
        "confirm_password": "ClaveSegura123",
        "telefono": "3001234567",
        "direccion": "Calle 1",
        "tipo_generador": "hogar",
    })
    assert response.status_code == 201
    assert response.json()["rol"] == "residente"
    with Session(database) as session:
        user = session.scalar(select(Usuario).where(Usuario.correo == "nuevo@example.invalid"))
        assert user is not None
        assert user.password_hash.startswith("scrypt$")
        assert user.rol == "residente"
        assert user.activo
        assert not user.piloto_habilitado


def test_public_registration_duplicate_and_role_tampering(database, client):
    body = {
        "nombre": "Residente Nuevo",
        "correo": "duplicado@example.invalid",
        "password": "ClaveSegura123",
        "confirm_password": "ClaveSegura123",
    }
    assert client.post("/auth/register", json=body).status_code == 201
    assert client.post("/auth/register", json=body).status_code == 409
    assert client.post("/auth/register", json={**body, "correo": "tamper@example.invalid", "rol": "administrador"}).status_code == 422


def test_admin_can_create_resident(database, client, headers):
    response = client.post("/usuarios", headers=headers["admin@example.invalid"], json={
        "nombre": "Residente Administrativo",
        "correo": "admin-create@example.invalid",
        "password": "ClaveSegura123",
        "confirm_password": "ClaveSegura123",
        "rol": "residente",
        "activo": True,
        "piloto_habilitado": False,
        "tipo_generador": "negocio",
    })
    assert response.status_code == 201
    assert response.json()["rol"] == "residente"


def test_resident_cannot_manage_users(database, client, headers):
    response = client.get("/usuarios", headers=headers["residente.reciclaje@example.invalid"])
    assert response.status_code == 403
