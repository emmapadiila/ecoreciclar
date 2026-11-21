"""Pruebas del webhook de WhatsApp sobre PostgreSQL real (fixtures del conftest).

Mapa a la matriz del equipo:
- T03: saludo devuelve el menú.
- T04: el reintento con el mismo meta_message_id no reprocesa (vía HTTP firmado,
  complementa la prueba a nivel de servicio de Ángel).
- Seguridad: challenge con token incorrecto -> 403; firma inválida o ausente
  -> 403; sin META_APP_SECRET -> 403 (fail closed); JSON inválido -> 400.
- Flujo: mensaje registrado, contenido guardado, respuesta del bot auditada
  como mensaje saliente, remitente nuevo registrado sin piloto habilitado.

Requisitos (venv activo, desde la raíz del repo):
    python -m scripts.create_test_db
    python -m scripts.provision_runtime --test
    pytest tests/test_whatsapp.py -v
"""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.main import app
from backend.models import Conversacion, MensajeWhatsapp, Usuario
from backend.whatsapp import (
    MENSAJE_MENU,
    RESPUESTA_FOTO,
    MensajeEntrante,
    extraer_mensajes,
    responder,
    router as whatsapp_router,
    verificar_firma,
)

TOKEN_PRUEBA = "token_de_verificacion_prueba"
SECRETO_PRUEBA = "secreto_de_firma_prueba"
WA_DEMO = "DEMO-WA-REC"  # residente de reciclaje del seed, piloto_habilitado=true
WA_NUEVO = "DEMO-WEBHOOK-NUEVO"


@pytest.fixture(autouse=True)
def whatsapp_entorno(monkeypatch):
    """Variables de entorno del webhook para toda prueba de este módulo."""
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", TOKEN_PRUEBA)
    monkeypatch.setenv("META_APP_SECRET", SECRETO_PRUEBA)
    monkeypatch.delenv("WHATSAPP_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("WHATSAPP_PHONE_NUMBER_ID", raising=False)
    yield


@pytest.fixture(autouse=True)
def webhook_montado():
    """Monta el router en la app real si Breiner aún no lo incluyó en main.py.

    Cuando main.py monte el router, la guarda evita duplicar la ruta.
    """
    if not any(
        getattr(ruta, "path", None) == "/webhooks/whatsapp" for ruta in app.routes
    ):
        app.include_router(whatsapp_router)
    yield


def _payload(
    mensaje_id: str, texto: str = "Hola", remitente: str = WA_DEMO, tipo: str = "text"
) -> dict:
    cuerpo = {
        "from": remitente,
        "id": mensaje_id,
        "timestamp": "1763700000",
        "type": tipo,
    }
    if tipo == "text":
        cuerpo["text"] = {"body": texto}
    elif tipo == "image":
        cuerpo["image"] = {"id": "MEDIA1", "mime_type": "image/jpeg"}
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "ENTRADA_DEMO",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"phone_number_id": "TELEFONO_DEMO"},
                            "contacts": [
                                {"profile": {"name": "Demo"}, "wa_id": remitente}
                            ],
                            "messages": [cuerpo],
                        },
                    }
                ],
            }
        ],
    }


def _cuerpo_firmado(payload: dict) -> tuple[bytes, dict]:
    cuerpo = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    firma = (
        "sha256="
        + hmac.new(SECRETO_PRUEBA.encode("utf-8"), cuerpo, hashlib.sha256).hexdigest()
    )
    return cuerpo, {"Content-Type": "application/json", "X-Hub-Signature-256": firma}


def _post(client: TestClient, payload: dict, firma: str | None = "valida"):
    cuerpo, encabezados = _cuerpo_firmado(payload)
    if firma is None:
        encabezados = {"Content-Type": "application/json"}
    elif firma == "invalida":
        encabezados = {
            "Content-Type": "application/json",
            "X-Hub-Signature-256": "sha256=" + "0" * 64,
        }
    return client.post("/webhooks/whatsapp", content=cuerpo, headers=encabezados)


# ----------------------------- seguridad -------------------------------------


def test_challenge_exitoso(client):
    respuesta = client.get(
        "/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": TOKEN_PRUEBA,
            "hub.challenge": "reto123",
        },
    )
    assert respuesta.status_code == 200
    assert respuesta.text == "reto123"


def test_challenge_token_incorrecto(client):
    respuesta = client.get(
        "/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "otro_token",
            "hub.challenge": "reto123",
        },
    )
    assert respuesta.status_code == 403


def test_post_sin_encabezado_de_firma(client):
    assert _post(client, _payload("DEMO-webhook-sf"), firma=None).status_code == 403


def test_post_firma_invalida(client):
    assert (
        _post(client, _payload("DEMO-webhook-fi"), firma="invalida").status_code == 403
    )


def test_firma_fail_closed_sin_secreto(client, monkeypatch):
    monkeypatch.delenv("META_APP_SECRET", raising=False)
    assert _post(client, _payload("DEMO-webhook-fc")).status_code == 403


def test_post_json_invalido_con_firma_valida(client):
    cuerpo = b"esto no es json"
    firma = (
        "sha256="
        + hmac.new(SECRETO_PRUEBA.encode("utf-8"), cuerpo, hashlib.sha256).hexdigest()
    )
    respuesta = client.post(
        "/webhooks/whatsapp",
        content=cuerpo,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": firma},
    )
    assert respuesta.status_code == 400


def test_verificar_firma_unidad():
    cuerpo = b'{"objeto": "prueba"}'
    firma = "sha256=" + hmac.new(b"secreto", cuerpo, hashlib.sha256).hexdigest()
    import os as _os

    _os.environ["META_APP_SECRET"] = "secreto"
    try:
        assert verificar_firma(cuerpo, firma)
        assert not verificar_firma(cuerpo, "sha256=" + "0" * 64)
        assert not verificar_firma(cuerpo, None)
    finally:
        del _os.environ["META_APP_SECRET"]


# ----------------------------- flujo T04 y auditoría --------------------------


def test_post_firma_valida_registra_y_procesa(database, client):
    respuesta = _post(client, _payload("DEMO-webhook-1"))
    assert respuesta.status_code == 200
    assert respuesta.json() == {"success": True, "nuevos": 1}
    with Session(database) as session:
        mensaje = session.scalar(
            select(MensajeWhatsapp).where(
                MensajeWhatsapp.meta_message_id == "DEMO-webhook-1"
            )
        )
        assert mensaje is not None
        assert mensaje.direccion == "entrante"
        assert mensaje.tipo == "texto"
        assert mensaje.contenido == "Hola"
        # El procesamiento en fondo ya corrió dentro de TestClient.
        assert mensaje.estado_procesamiento == "procesado"
        saliente = session.scalar(
            select(MensajeWhatsapp).where(
                MensajeWhatsapp.conversacion_id == mensaje.conversacion_id,
                MensajeWhatsapp.direccion == "saliente",
            )
        )
        assert saliente is not None
        assert saliente.contenido.startswith("Hola, soy el asistente")
        # Sin credenciales de Meta en pruebas: el envío falla de forma honesta.
        assert saliente.estado_envio == "fallido"
        assert saliente.meta_message_id.startswith("saliente-sin-entrega-")


def test_reintento_no_reprocesa_t04(database, client):
    assert _post(client, _payload("DEMO-webhook-2")).json()["nuevos"] == 1
    assert _post(client, _payload("DEMO-webhook-2")).json()["nuevos"] == 0
    with Session(database) as session:
        entrantes = session.scalar(
            select(func.count())
            .select_from(MensajeWhatsapp)
            .where(MensajeWhatsapp.meta_message_id == "DEMO-webhook-2")
        )
        salientes = session.scalar(
            select(func.count())
            .select_from(MensajeWhatsapp)
            .where(MensajeWhatsapp.direccion == "saliente")
        )
    assert entrantes == 1
    assert salientes == 1


def test_recibo_de_estado_no_procesa(client):
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "E",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "statuses": [{"id": "DEMO-status", "status": "delivered"}],
                        },
                    }
                ],
            }
        ],
    }
    assert _post(client, payload).json()["nuevos"] == 0


def test_remitente_nuevo_sin_piloto_habilitado(database, client):
    respuesta = _post(client, _payload("DEMO-webhook-3", remitente=WA_NUEVO))
    assert respuesta.json()["nuevos"] == 1
    with Session(database) as session:
        usuario = session.scalar(select(Usuario).where(Usuario.whatsapp_id == WA_NUEVO))
        assert usuario is not None
        assert not usuario.piloto_habilitado  # según docs/arquitectura.md
        assert usuario.rol == "residente"


def test_imagen_se_registra_sin_contenido(database, client):
    assert _post(client, _payload("DEMO-webhook-4", tipo="image")).json()["nuevos"] == 1
    with Session(database) as session:
        mensaje = session.scalar(
            select(MensajeWhatsapp).where(
                MensajeWhatsapp.meta_message_id == "DEMO-webhook-4"
            )
        )
        assert mensaje.tipo == "imagen"
        assert mensaje.contenido is None  # privacidad: no se guarda media
        assert mensaje.estado_procesamiento == "procesado"


# ----------------------------- parser y respuestas -----------------------------


def test_parser_tipos():
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messages": [
                                {
                                    "from": WA_DEMO,
                                    "id": "m1",
                                    "type": "text",
                                    "text": {"body": "Hola"},
                                },
                                {
                                    "from": WA_DEMO,
                                    "id": "m2",
                                    "type": "image",
                                    "image": {
                                        "id": "MEDIA1",
                                        "mime_type": "image/jpeg",
                                    },
                                },
                                {
                                    "from": WA_DEMO,
                                    "id": "m3",
                                    "type": "interactive",
                                    "interactive": {
                                        "type": "button_reply",
                                        "button_reply": {
                                            "id": "b1",
                                            "title": "Agendar",
                                        },
                                    },
                                },
                            ]
                        },
                    }
                ]
            }
        ]
    }
    eventos = extraer_mensajes(payload)
    assert [e.tipo for e in eventos] == ["text", "image", "interactive"]
    assert eventos[0].texto == "Hola"
    assert eventos[1].media_id == "MEDIA1"
    assert eventos[2].titulo_boton == "Agendar"


def test_t03_saludo_devuelve_menu():
    mensaje = MensajeWhatsapp(tipo="texto", contenido="Hola")
    assert MENSAJE_MENU in responder(mensaje, Conversacion(), Usuario())


def test_respuesta_foto_honesta():
    mensaje = MensajeWhatsapp(tipo="imagen")
    assert responder(mensaje, Conversacion(), Usuario()) == RESPUESTA_FOTO


def test_contrato_imagen_y_recibo_firmado(client, database, monkeypatch):
    from backend import whatsapp, whatsapp_meta
    from datetime import datetime, timezone
    muestra = b"\xff\xd8\xffsimulada"
    marca = object()
    def analizar(datos, mime):
        assert (datos, mime) == (muestra, "image/jpeg")
        return marca
    def chatbot(session, usuario, conversacion, evento):
        assert evento.analisis_imagen is marca
        assert usuario.id == conversacion.usuario_id
        return ["Recibido"]
    monkeypatch.setattr(app.state, "analizar_imagen", analizar, raising=False)
    monkeypatch.setattr(app.state, "procesar_evento", chatbot, raising=False)
    monkeypatch.setattr(whatsapp, "descargar_imagen", lambda _: muestra)
    monkeypatch.setattr(whatsapp_meta, "enviar", lambda *args: "wamid.respuesta")
    payload = _payload("wamid.imagen", tipo="image")
    valor = payload["entry"][0]["changes"][0]["value"]
    valor["messages"][0]["timestamp"] = str(int(datetime.now(timezone.utc).timestamp()))
    assert _post(client, payload).json()["nuevos"] == 1
    del valor["messages"]
    valor["statuses"] = [{"id": "wamid.respuesta", "status": "delivered"}]
    assert _post(client, payload).json()["nuevos"] == 0
    with Session(database) as session:
        assert session.scalar(select(MensajeWhatsapp.estado_envio).where(
            MensajeWhatsapp.meta_message_id == "wamid.respuesta")) == "entregado"


def test_estructura_invalida(client):
    assert _post(client, {"entry": [None]}).status_code == 400


def test_reintento_tras_rollback_del_chatbot(client, database, monkeypatch):
    from backend.models import Notificacion
    payload = _payload("wamid.rollback")
    def falla(session, usuario, conv, evento):
        conv.estado_actual = "no_confirmado"
        raise RuntimeError()
    monkeypatch.setattr(app.state, "procesar_evento", falla, raising=False)
    assert _post(client, payload).status_code == 503
    with Session(database) as session:
        assert session.scalar(select(MensajeWhatsapp.estado_procesamiento).where(
            MensajeWhatsapp.meta_message_id == "wamid.rollback")) == "pendiente"
        assert session.scalar(select(Notificacion.id).where(Notificacion.tipo == "respuesta")) is None
        assert session.scalar(select(Conversacion.id).where(Conversacion.estado_actual == "no_confirmado")) is None
    monkeypatch.delattr(app.state, "procesar_evento")
    assert _post(client, payload).json() == {"success": True, "nuevos": 0}
    with Session(database) as session:
        assert session.scalar(select(MensajeWhatsapp.estado_procesamiento).where(
            MensajeWhatsapp.meta_message_id == "wamid.rollback")) == "procesado"
