from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from threading import Barrier

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.auth import hash_password
from backend.models import (
    Asignacion, Colectivo, Conversacion, HistorialEstado, Material, MensajeWhatsapp,
    MovimientoPuntos, Notificacion, Recoleccion, Recolector, ReglaPuntos, Solicitud, Usuario,
)
from backend.services import close_collection, register_verified_message, set_actor


def approve(database):
    with Session(database) as session, session.begin():
        admin = session.scalar(select(Usuario).where(Usuario.correo == "admin@example.invalid"))
        set_actor(session, admin.id)
        for rule in session.scalars(select(ReglaPuntos)):
            rule.aprobada = True
            rule.aprobada_por = admin.id


def ids(database, flow="reciclable"):
    with Session(database) as session:
        cid = session.scalar(select(Colectivo.id).where(Colectivo.tipo_flujo == flow))
        rid = session.scalar(select(Recolector.id).where(Recolector.colectivo_id == cid))
        mid = session.scalar(select(Material.id).where(Material.categoria == flow, Material.aceptado))
        sid = session.scalar(select(Solicitud.id).where(Solicitud.colectivo_id == cid))
        return cid, rid, mid, sid


def count(database, model):
    with Session(database) as session:
        return session.scalar(select(func.count()).select_from(model))


def test_collectors_are_restricted_to_coordinator_collective(database, client, headers):
    recycling_id, recycling_collector, _, _ = ids(database, "reciclable")
    organic_id, organic_collector, _, _ = ids(database, "organico")
    response = client.get("/recolectores", headers=headers["coordinador.reciclaje@example.invalid"])
    assert response.status_code == 200
    assert recycling_collector in [worker["id"] for worker in response.json()]
    assert all(worker["colectivo_id"] == recycling_id for worker in response.json())
    assert organic_collector not in [worker["id"] for worker in response.json()]
    response = client.get("/recolectores", headers=headers["coordinador.huerta@example.invalid"])
    assert response.status_code == 200
    assert organic_collector in [worker["id"] for worker in response.json()]
    assert all(worker["colectivo_id"] == organic_id for worker in response.json())
    assert client.get("/recolectores", headers=headers["residente.reciclaje@example.invalid"]).status_code == 403
    assert client.get("/recolectores").status_code == 401


@pytest.mark.parametrize("flow,suffix,expected", [("reciclable", "reciclaje", "50.00"), ("organico", "huerta", "25.00")])
def test_complete_api_flow(database, client, headers, flow, suffix, expected):
    approve(database)
    cid, collector, material, _ = ids(database, flow)
    resident = headers[f"residente.{suffix}@example.invalid"]
    coordinator = headers[f"coordinador.{suffix}@example.invalid"]
    response = client.post("/solicitudes", headers=resident, json={
        "direccion": "DEMO dirección ficticia", "materiales": [{"material_id": material, "estimado_kg": "999", "confirmado": True}],
    })
    assert response.status_code == 201, response.text
    request = response.json()
    sid = request["id"]
    assert request["colectivo_id"] == cid
    assert client.get("/mi-cuenta/puntos", headers=resident).json()["puntos"] in ("0", "0.00")
    assert client.post(f"/solicitudes/{sid}/asignacion", headers=coordinator, json={"recolector_id": collector}).status_code == 201
    response = client.post(f"/solicitudes/{sid}/programacion", headers=coordinator, json={"programada_en": "2030-01-15T09:00:00-05:00"})
    assert response.status_code == 200, response.text
    assert count(database, MovimientoPuntos) == 0
    response = client.post(f"/solicitudes/{sid}/cierre", headers=coordinator, json={"peso_real_kg": "5.00"})
    assert response.status_code == 200, response.text
    assert response.json()["puntos"] == expected  # Peso confirmado, no estimado.
    assert client.post(f"/solicitudes/{sid}/cierre", headers=coordinator, json={"peso_real_kg": "5"}).status_code == 409
    assert client.get("/mi-cuenta/puntos", headers=resident).json()["puntos"] == expected
    history = client.get(f"/solicitudes/{sid}/historial", headers=coordinator).json()
    assert [h["nuevo"] for h in history] == ["recibida", "asignada", "programada", "recolectada"]
    assert all(h["actor_id"] and h["fecha"] for h in history)
    with Session(database) as session:
        assert session.get(Solicitud, sid).estado == "recolectada"
        assignment = session.scalar(select(Asignacion).where(Asignacion.solicitud_id == sid))
        assert assignment.programada_en.hour == 14  # 09:00 Bogotá -> 14:00 UTC.
        assert count(database, MovimientoPuntos) == 1
        assert session.scalar(select(func.count()).select_from(Notificacion).where(Notificacion.solicitud_id == sid)) == 2


def test_seed_is_idempotent_and_unapproved(database):
    before = count(database, Solicitud), count(database, Usuario), count(database, HistorialEstado)
    with database.begin() as connection:
        connection.exec_driver_sql(Path("database/seed_demo.sql").read_text(encoding="utf-8"))
    assert before == (count(database, Solicitud), count(database, Usuario), count(database, HistorialEstado))
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(ReglaPuntos).where(ReglaPuntos.aprobada)) == 0
    assert count(database, MovimientoPuntos) == 0


def test_cross_collective_access_forbidden(database, client, headers):
    _, collector, _, sid = ids(database, "organico")
    auth = headers["coordinador.reciclaje@example.invalid"]
    for path in (f"/solicitudes/{sid}", f"/solicitudes/{sid}/historial"):
        assert client.get(path, headers=auth).status_code == 404
    for action, payload in (
        ("asignacion", {"recolector_id": collector}),
        ("programacion", {"programada_en": "2030-01-15T09:00:00-05:00"}),
        ("cierre", {"peso_real_kg": "5"}),
        ("estado", {"estado": "cancelada", "observacion": "DEMO"}),
    ):
        assert client.post(f"/solicitudes/{sid}/{action}", headers=auth, json=payload).status_code == 404
    assert all(s["id"] != sid for s in client.get("/solicitudes", headers=auth).json())
    assert client.get(f"/solicitudes/{sid}", headers=headers["residente.reciclaje@example.invalid"]).status_code == 404


def test_authentication_and_disabled_pilot(database, client, headers):
    assert client.get("/solicitudes").status_code == 401
    assert client.get("/solicitudes", headers={"Authorization": "Bearer forged"}).status_code == 401
    with Session(database) as session, session.begin():
        user = session.scalar(select(Usuario).where(Usuario.correo == "residente.reciclaje@example.invalid"))
        user.password_hash = hash_password("DEMO-password-only-in-test")
    response = client.post("/auth/token", json={"correo": "residente.reciclaje@example.invalid", "password": "DEMO-password-only-in-test"})
    assert response.status_code == 200
    assert client.get("/solicitudes", headers={"Authorization": "Bearer " + response.json()["access_token"]}).status_code == 200
    assert client.post("/auth/token", json={"correo": "admin@example.invalid", "password": "wrong"}).status_code == 401
    with Session(database) as session, session.begin():
        user = session.scalar(select(Usuario).where(Usuario.correo == "residente.reciclaje@example.invalid"))
        user.piloto_habilitado = False
    auth = headers["residente.reciclaje@example.invalid"]
    assert client.get("/solicitudes", headers=auth).status_code == 401
    assert client.post("/solicitudes", headers=auth, json={"direccion": "DEMO", "materiales": [{"material_id": 1, "confirmado": True}]}).status_code == 401


def test_message_identity_and_retries(database):
    with Session(database) as session, session.begin():
        first, msg, created = register_verified_message(session, "DEMO-WA-REC", "DEMO-msg-1", "texto")
        uid, mid = first.id, msg.id
        assert created
        first_id = first.id
    with Session(database) as session, session.begin():
        again, msg, created = register_verified_message(session, "DEMO-WA-REC", "DEMO-msg-1", "texto")
        assert (again.id, msg.id, created) == (uid, mid, False)
        conversation = session.scalar(select(Conversacion).where(Conversacion.usuario_id == uid))
        conversation.datos_temporales = {}  # Reiniciar chatbot no borra identidad.
        conversation.estado_actual = "inicio"
    with Session(database) as session, session.begin():
        third, _, _ = register_verified_message(session, "DEMO-WA-REC", "DEMO-msg-2", "imagen")
        assert third.id == first_id
        assert session.scalar(select(func.count()).select_from(Solicitud).where(Solicitud.usuario_id == uid)) == 1
        new, _, _ = register_verified_message(session, "DEMO-NEW", "DEMO-msg-3", "texto")
        assert not new.piloto_habilitado
    assert count(database, MensajeWhatsapp) == 3


def test_concurrent_message_delivery(database):
    barrier = Barrier(2)
    def receive():
        with Session(database) as session, session.begin():
            barrier.wait(timeout=10)
            user, message, created = register_verified_message(session, "DEMO-CONCURRENT", "DEMO-concurrent", "texto")
            return user.id, message.id, created
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: receive(), range(2)))
    assert results[0][:2] == results[1][:2]
    assert sorted(r[2] for r in results) == [False, True]
    assert count(database, MensajeWhatsapp) == 1


@pytest.mark.parametrize("material_names", [
    ["DEMO Botellas PET", "DEMO Restos vegetales"], ["DEMO Material rechazado"], ["DEMO Residuo desconocido"],
])
def test_invalid_materials_not_routed(database, client, headers, material_names):
    with Session(database) as session:
        materials = list(session.scalars(select(Material.id).where(Material.nombre.in_(material_names))))
    response = client.post("/solicitudes", headers=headers["residente.reciclaje@example.invalid"], json={
        "direccion": "DEMO", "materiales": [{"material_id": mid, "confirmado": True} for mid in materials],
    })
    assert response.status_code == 422
    assert count(database, Solicitud) == 2


@pytest.mark.parametrize("wrong_kind", ["other_collective", "inactive", "unconfirmed"])
def test_invalid_assignment_rolls_back(database, client, headers, wrong_kind):
    _, collector, material, _ = ids(database)
    if wrong_kind == "other_collective":
        _, collector, _, _ = ids(database, "organico")
    elif wrong_kind == "inactive":
        with Session(database) as session, session.begin():
            session.get(Recolector, collector).activo = False
    response = client.post("/solicitudes", headers=headers["residente.reciclaje@example.invalid"], json={
        "direccion": "DEMO", "materiales": [{"material_id": material, "confirmado": wrong_kind != "unconfirmed"}],
    })
    sid = response.json()["id"]
    response = client.post(f"/solicitudes/{sid}/asignacion", headers=headers["coordinador.reciclaje@example.invalid"], json={"recolector_id": collector})
    assert response.status_code == 409, response.text
    with Session(database) as session:
        assert session.get(Solicitud, sid).estado == "recibida"
        assert session.scalar(select(Asignacion).where(Asignacion.solicitud_id == sid)) is None


@pytest.mark.parametrize("payload", [{}, {"programada_en": "2030-01-01"}, {"programada_en": "2030-01-01T10:00:00"}])
def test_schedule_requires_datetime_timezone(database, client, headers, payload):
    sid = ids(database)[3]
    response = client.post(f"/solicitudes/{sid}/programacion", headers=headers["coordinador.reciclaje@example.invalid"], json=payload)
    assert response.status_code == 422


@pytest.mark.parametrize("weight", ["0", "-1", "NaN", "Infinity", "1.001"])
def test_close_requires_valid_weight(database, client, headers, weight):
    sid = ids(database)[3]
    response = client.post(f"/solicitudes/{sid}/cierre", headers=headers["coordinador.reciclaje@example.invalid"], json={"peso_real_kg": weight})
    assert response.status_code == 422
    assert count(database, Recoleccion) == 0


def test_unapproved_rule_rolls_back_entire_close(database, client, headers):
    sid = ids(database)[3]
    before = count(database, HistorialEstado), count(database, Notificacion)
    response = client.post(f"/solicitudes/{sid}/cierre", headers=headers["coordinador.reciclaje@example.invalid"], json={"peso_real_kg": "5"})
    assert response.status_code == 409
    assert count(database, Recoleccion) == count(database, MovimientoPuntos) == 0
    assert before == (count(database, HistorialEstado), count(database, Notificacion))
    with Session(database) as session:
        assert session.get(Solicitud, sid).estado == "programada"


def test_concurrent_close_credits_once(database):
    approve(database)
    sid = ids(database)[3]
    barrier = Barrier(2)
    def close():
        try:
            with Session(database) as session, session.begin():
                user = session.scalar(select(Usuario).where(Usuario.correo == "coordinador.reciclaje@example.invalid"))
                barrier.wait(timeout=10)
                close_collection(session, user, sid, Decimal("5"))
            return "closed"
        except HTTPException as exc:
            return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: close(), range(2)))
    assert results.count("closed") == 1 and results.count(409) == 1
    assert count(database, Recoleccion) == count(database, MovimientoPuntos) == 1


@pytest.mark.parametrize("sql", [
    "INSERT INTO usuarios(nombre,whatsapp_id) VALUES('DEMO duplicate','DEMO-WA-REC')",
    "INSERT INTO conversaciones(usuario_id) VALUES(999999)",
    "UPDATE solicitudes SET estado='programada' WHERE id=1",  # Falta actor.
    "UPDATE historial_estados SET estado_nuevo='cancelada' WHERE id=1",
    "DELETE FROM historial_estados WHERE id=1",
    "INSERT INTO mensajes_whatsapp(conversacion_id,meta_message_id,direccion,tipo) VALUES(999999,'DEMO','entrante','texto')",
])
def test_database_integrity_rejects_direct_sql(database, sql):
    with pytest.raises(IntegrityError):
        with database.begin() as conn:
            conn.execute(text(sql))


def test_fabricated_history_is_rejected(database):
    with pytest.raises(IntegrityError):
        with database.begin() as conn:
            conn.execute(text("INSERT INTO historial_estados(solicitud_id,usuario_actor_id,estado_nuevo) VALUES(1,1,'recolectada')"))


@pytest.mark.parametrize("kind", ["wrong_owner", "wrong_collective", "wrong_amount", "no_collection"])
def test_forged_points_are_rejected(database, kind):
    approve(database)
    with pytest.raises(IntegrityError):
        with Session(database) as session, session.begin():
            user = session.scalar(select(Usuario).where(Usuario.correo == "coordinador.reciclaje@example.invalid"))
            request = session.scalar(select(Solicitud).where(Solicitud.codigo == "DEMO-ECO-REC"))
            assignment = session.scalar(select(Asignacion).where(Asignacion.solicitud_id == request.id))
            rule = session.scalar(select(ReglaPuntos).where(ReglaPuntos.colectivo_id == request.colectivo_id))
            set_actor(session, user.id)
            collection_id = 999999
            if kind != "no_collection":
                collection = Recoleccion(solicitud_id=request.id, asignacion_id=assignment.id,
                                         peso_real_kg=Decimal("5"), registrado_por=user.id)
                session.add(collection)
                session.flush()
                collection_id = collection.id
            if kind == "wrong_collective":
                rule = session.scalar(select(ReglaPuntos).where(ReglaPuntos.colectivo_id != request.colectivo_id))
            session.add(MovimientoPuntos(usuario_id=user.id if kind == "wrong_owner" else request.usuario_id,
                recoleccion_id=collection_id, regla_id=rule.id,
                puntos=Decimal("500") if kind == "wrong_amount" else Decimal("50"), concepto="DEMO intento inválido"))
            session.flush()
    assert count(database, Recoleccion) == count(database, MovimientoPuntos) == 0


def test_request_schedule_without_assignment_is_rejected(database, client, headers):
    material = ids(database)[2]
    response = client.post("/solicitudes", headers=headers["residente.reciclaje@example.invalid"], json={
        "direccion": "DEMO", "materiales": [{"material_id": material, "confirmado": True}],
    })
    sid = response.json()["id"]
    assert client.post(f"/solicitudes/{sid}/programacion", headers=headers["coordinador.reciclaje@example.invalid"],
                       json={"programada_en": "2030-01-01T09:00:00-05:00"}).status_code == 409


def test_request_without_pilot_authorization_rejected_in_database(database):
    with pytest.raises(IntegrityError):
        with Session(database) as session, session.begin():
            user = session.scalar(select(Usuario).where(Usuario.correo == "residente.reciclaje@example.invalid"))
            user.piloto_habilitado = False
            session.flush()
            set_actor(session, user.id)
            session.add(Solicitud(codigo="DEMO-NO-AUTH", usuario_id=user.id, colectivo_id=ids(database)[0],
                                  tipo_generador="hogar", direccion="DEMO", origen="web"))
            session.flush()


def test_nullable_whatsapp_and_code_unique(database):
    with database.begin() as conn:
        conn.execute(text("INSERT INTO usuarios(nombre) VALUES('DEMO web 1'),('DEMO web 2')"))
    with pytest.raises(IntegrityError):
        with database.begin() as conn:
            conn.execute(text("SELECT set_config('app.actor_id','1',true)"))
            conn.execute(text("INSERT INTO solicitudes(codigo,usuario_id,colectivo_id,tipo_generador,direccion,origen) SELECT codigo,usuario_id,colectivo_id,tipo_generador,direccion,origen FROM solicitudes WHERE codigo='DEMO-ECO-REC'"))


def test_direct_close_without_points_fails_at_commit(database):
    with pytest.raises(IntegrityError):
        with Session(database) as session, session.begin():
            user = session.scalar(select(Usuario).where(Usuario.correo == "coordinador.reciclaje@example.invalid"))
            set_actor(session, user.id)
            assignment = session.scalar(select(Asignacion).join(Solicitud, Asignacion.solicitud_id == Solicitud.id).where(Solicitud.codigo == "DEMO-ECO-REC"))
            session.add(Recoleccion(solicitud_id=assignment.solicitud_id, asignacion_id=assignment.id,
                                    peso_real_kg=Decimal("5"), registrado_por=user.id))
            session.flush()  # INSERT permitido; COMMIT debe rechazar el cierre incompleto.
    assert count(database, Recoleccion) == 0
    with Session(database) as session:
        assert session.scalar(select(Solicitud.estado).where(Solicitud.codigo == "DEMO-ECO-REC")) == "programada"


def test_duplicate_and_tampered_points_blocked(database, client, headers):
    approve(database)
    sid = ids(database)[3]
    assert client.post(f"/solicitudes/{sid}/cierre", headers=headers["coordinador.reciclaje@example.invalid"], json={"peso_real_kg": "5"}).status_code == 200
    for sql in (
        "UPDATE movimientos_puntos SET puntos=500",
        "DELETE FROM movimientos_puntos",
        "UPDATE recolecciones SET peso_real_kg=50",
        "INSERT INTO movimientos_puntos(usuario_id,recoleccion_id,regla_id,puntos,concepto) SELECT usuario_id,recoleccion_id,regla_id,puntos,concepto FROM movimientos_puntos",
    ):
        with pytest.raises(IntegrityError):
            with Session(database) as session, session.begin():
                user = session.scalar(select(Usuario).where(Usuario.correo == "coordinador.reciclaje@example.invalid"))
                set_actor(session, user.id)
                session.execute(text(sql))
    assert count(database, MovimientoPuntos) == 1


def test_expired_rule_and_overlap(database, client, headers):
    with Session(database) as session, session.begin():
        admin = session.scalar(select(Usuario).where(Usuario.rol == "administrador"))
        set_actor(session, admin.id)
        for rule in session.scalars(select(ReglaPuntos)):
            rule.fecha_fin = datetime(2021, 1, 1, tzinfo=timezone.utc)
            rule.aprobada = True
            rule.aprobada_por = admin.id
    sid = ids(database)[3]
    assert client.post(f"/solicitudes/{sid}/cierre", headers=headers["coordinador.reciclaje@example.invalid"], json={"peso_real_kg": "5"}).status_code == 409
    with pytest.raises(IntegrityError):
        with Session(database) as session, session.begin():
            admin = session.scalar(select(Usuario).where(Usuario.rol == "administrador"))
            set_actor(session, admin.id)
            session.execute(text("INSERT INTO reglas_puntos(colectivo_id,puntos_por_kg,fecha_inicio,fecha_fin,aprobada,aprobada_por) SELECT colectivo_id,1,'2020-06-01','2020-12-01',true,aprobada_por FROM reglas_puntos LIMIT 1"))
