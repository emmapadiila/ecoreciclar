import hashlib
import hmac
import json

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend import services, whatsapp
from backend.conversacion import procesar_evento
from backend.main import app
from backend.models import (
    Colectivo, Material, MovimientoPuntos, Notificacion, Solicitud, SolicitudMaterial, Usuario,
)
from test_conversacion import charla
from test_workflows import approve, prepare_seeded_close


def solicitudes_nuevas(session):
    return list(session.scalars(select(Solicitud).where(Solicitud.codigo.not_like("DEMO-%")).order_by(Solicitud.id)))


def completar_borrador(chat, materiales):
    assert chat(materiales)[0] == "revision_material"
    for entrada, paso in (("1", "direccion"), ("1", "horario"),
                          ("Mañana", "observaciones"), ("omitir", "confirmacion")):
        assert chat(entrada)[0] == paso


@pytest.mark.parametrize("materiales,categorias", [
    ("Tengo restos vegetales", {"organico"}),
    ("Tengo botellas plásticas", {"reciclable"}),
    ("Tengo restos vegetales y botellas plásticas", {"organico", "reciclable"}),
])
def test_confirmacion_real_y_enrutamiento(database, charla, materiales, categorias):
    completar_borrador(charla, materiales)
    with Session(database) as session:
        assert not solicitudes_nuevas(session)
    assert charla("2")[0] == "editar"
    assert charla("2")[0] == "direccion_nueva"
    assert "Dirección de prueba 123" in charla("Dirección de prueba 123")[1]
    mensaje = charla("Confirmar solicitud")[1]
    with Session(database) as session:
        items = solicitudes_nuevas(session)
        assert len(items) == len(categorias)
        assert {session.get(Colectivo, item.colectivo_id).tipo_flujo for item in items} == categorias
        for item in items:
            assert item.origen == "whatsapp" and item.estado == "recibida"
            assert item.codigo.startswith("ECO-") and item.codigo in mensaje
            assert item.direccion == "Dirección de prueba 123"
            assert session.get(Usuario, item.usuario_id).whatsapp_id == "DEMO-WA-REC"
            material = session.scalar(select(SolicitudMaterial).where(SolicitudMaterial.solicitud_id == item.id))
            assert material.confirmado and session.get(Material, material.material_id).aceptado
            flujo = session.get(Colectivo, item.colectivo_id).tipo_flujo
            sufijo = "reciclaje" if flujo == "reciclable" else "huerta"
            coordinador = session.scalar(select(Usuario).where(Usuario.correo == f"coordinador.{sufijo}@example.invalid"))
            assert item in session.scalars(services.scoped_requests(coordinador)).all()
        assert session.scalar(select(func.count()).select_from(MovimientoPuntos)) == 0


@pytest.mark.parametrize("caso", ["cancelar", "material inactivo", "cuenta inactiva", "colectivo inactivo"])
def test_confirmacion_no_persiste_si_falla(database, charla, caso):
    completar_borrador(charla, "Tengo botellas plásticas y restos vegetales")
    with Session(database) as session, session.begin():
        if caso == "material inactivo":
            session.scalar(select(Material).where(Material.nombre == "DEMO Botellas PET")).activo = False
        if caso == "cuenta inactiva":
            session.scalar(select(Usuario).where(Usuario.whatsapp_id == "DEMO-WA-REC")).activo = False
        if caso == "colectivo inactivo":
            session.scalar(select(Colectivo).where(Colectivo.tipo_flujo == "reciclable")).activo = False
    assert "Código:" not in charla("3" if caso == "cancelar" else "1")[1]
    with Session(database) as session:
        assert not solicitudes_nuevas(session)


def test_solo_consulta_datos_propios_y_puntos_reales(database, charla):
    mensaje = charla("Consultar mis solicitudes")[1]
    assert "DEMO-ECO-REC" in mensaje and "DEMO-ECO-ORG" not in mensaje
    assert "DEMO-ECO-ORG" not in charla("Consultar DEMO-ECO-ORG")[1]
    assert "Saldo acumulado: 0" in charla("Consultar mis puntos")[1]
    approve(database)
    with Session(database) as session:
        sid = session.scalar(select(Solicitud.id).where(Solicitud.codigo == "DEMO-ECO-REC"))
    prepare_seeded_close(database, sid)
    with Session(database) as session, session.begin():
        user = session.scalar(select(Usuario).where(Usuario.correo == "coordinador.reciclaje@example.invalid"))
        services.close_collection(session, user, sid)
    assert "Saldo acumulado: 50.00" in charla("3")[1]
    assert "Saldo acumulado: 0" in charla("3", remitente="DEMO-WA-ORG")[1]


@pytest.mark.parametrize("corregir", [False, True])
def test_foto_mixta_separa_o_respeta_correccion(database, charla, corregir):
    assert charla("1")[0] == "tipo"
    assert charla("3")[0] == "metodo"
    assert charla("1")[0] == "espera_imagen"
    estado, mensaje = charla(imagen={"estado": "completado", "residuos": [
        {"id": "uno", "material": "PET", "categoria": "reciclable"},
        {"id": "dos", "nombre": "Cáscaras de fruta", "categoria": "organico"},
    ]})
    assert estado == "revision_material"
    assert "solicitudes separadas" in mensaje
    if corregir:
        assert charla("2")[0] == "materiales"
        assert charla("restos vegetales")[0] == "revision_material"
    for entrada in ("1", "1", "Tarde", "Sin observaciones"):
        estado, mensaje = charla(entrada)
    assert estado == "confirmacion"
    with Session(database) as session:
        assert not solicitudes_nuevas(session)
    assert "Código:" in charla("1")[1]
    with Session(database) as session:
        flujos = {session.get(Colectivo, item.colectivo_id).tipo_flujo for item in solicitudes_nuevas(session)}
        assert flujos == ({"organico"} if corregir else {"organico", "reciclable"})


def test_webhook_inyecta_chatbot_y_deduplica_confirmacion(client, database, monkeypatch):
    monkeypatch.setenv("META_APP_SECRET", "mock-firma-local")
    monkeypatch.delenv("WHATSAPP_PHONE_NUMBER_ID", raising=False)
    monkeypatch.setattr(app.state, "procesar_evento", procesar_evento, raising=False)
    monkeypatch.setattr(whatsapp.outbox, "despachar", lambda *_: None)

    def enviar(texto, numero):
        cuerpo = json.dumps({"entry": [{"changes": [{"field": "messages", "value": {"messages": [
            {"from": "DEMO-WA-REC", "id": f"wamid.demo-integracion-{numero}", "type": "text", "text": {"body": texto}},
        ]}}]}]}).encode()
        firma = hmac.new(b"mock-firma-local", cuerpo, hashlib.sha256).hexdigest()
        respuesta = client.post("/webhooks/whatsapp", content=cuerpo, headers={"X-Hub-Signature-256": "sha256=" + firma})
        assert respuesta.status_code == 200, respuesta.text
        return respuesta.json()["nuevos"]

    for i, texto in enumerate(("Hola", "Tengo botellas plásticas", "1", "1", "Mañana", "omitir", "1")):
        assert enviar(texto, i) == 1
    assert enviar("1", i) == 0
    with Session(database) as session:
        assert len(solicitudes_nuevas(session)) == 1
        assert len(session.scalars(select(Notificacion).where(
            Notificacion.tipo == "respuesta", Notificacion.mensaje.like("%Código:%"),
        )).all()) == 1
