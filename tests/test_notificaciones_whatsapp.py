from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend import notificaciones_whatsapp as worker, whatsapp_meta as meta
from backend.models import MensajeWhatsapp, Notificacion


def preparar(database, monkeypatch):
    monkeypatch.setenv("WHATSAPP_TEMPLATE_PROGRAMACION", "aviso_aprobado")
    monkeypatch.setenv("WHATSAPP_TEMPLATE_LANGUAGE", "es_CO")
    with Session(database) as session:
        return session.scalar(select(Notificacion.id).order_by(Notificacion.id))


def test_despacho_concurrente_y_estado(database, monkeypatch):
    nid = preparar(database, monkeypatch)
    solicitudes = []

    def enviar(destino, carga, referencia):
        with Session(database) as session:
            assert session.get(Notificacion, nid).estado == "incierta"
            assert session.scalar(select(MensajeWhatsapp).where(
                MensajeWhatsapp.meta_message_id == referencia)).notificacion_id == nid
        solicitudes.append(carga)
        with Session(database) as session, session.begin():
            worker.registrar_estado(session, {"id": "wamid.mock", "status": "read",
                                              "biz_opaque_callback_data": referencia})
        return "wamid.mock"

    monkeypatch.setattr(meta, "enviar", enviar)
    with ThreadPoolExecutor(2) as pool:
        list(pool.map(lambda _: worker.despachar(database, nid), range(2)))
    assert solicitudes == [{"type": "template", "template": {
        "name": "aviso_aprobado", "language": {"code": "es_CO"}}}]
    with Session(database) as session, session.begin():
        worker.registrar_estado(session, {"id": "wamid.mock", "status": "sent"})
        assert session.get(Notificacion, nid).intentos == 1
        assert session.scalar(select(MensajeWhatsapp.estado_envio)) == "leido"


@pytest.mark.parametrize("error,incierto", [(httpx.ConnectError, False), (httpx.ReadTimeout, True)])
def test_fallo_de_red(database, monkeypatch, error, incierto):
    nid = preparar(database, monkeypatch)
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "simulado")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "12345")
    from backend.models import Usuario
    with Session(database) as session, session.begin():
        session.get(Usuario, session.get(Notificacion, nid).usuario_id).whatsapp_id = "123456789"
    def simular(*args, **kwargs):
        raise error("simulado")
    monkeypatch.setattr(httpx.Client, "post", simular)
    for _ in range(3):
        worker.despachar(database, nid)
        with Session(database) as session, session.begin():
            nota = session.get(Notificacion, nid)
            if nota.estado == "pendiente":
                assert nota.proximo_intento > datetime.now(timezone.utc)
                nota.proximo_intento = datetime.now(timezone.utc) - timedelta(seconds=1)
    with Session(database) as session:
        nota = session.get(Notificacion, nid)
        assert nota.estado == ("incierta" if incierto else "fallida")
        assert nota.intentos == (1 if incierto else 3)
        assert all(a.error_envio for a in session.scalars(select(MensajeWhatsapp)))


@pytest.mark.parametrize("contenido,mime,esperado", [
    (b"texto", "image/png", False),
    (b"\x89PNG\r\n\x1a\n", "text/html", False),
    (b"\x89PNG\r\n\x1a\n" + bytes(20), "image/png", False),
    (b"\x89PNG\r\n\x1a\n" + bytes(8), "image/png", True),
])
def test_descarga_acotada(monkeypatch, contenido, mime, esperado):
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "simulado")
    monkeypatch.setattr(meta, "LIMITE", 16)
    def responder(req):
        if req.url.host == "graph.facebook.com":
            return httpx.Response(200, json={"mime_type": "image/png", "file_size": 1,
                                             "url": "https://lookaside.fbsbx.com/media"})
        return httpx.Response(200, content=contenido, headers={"Content-Type": mime})
    cliente = httpx.AsyncClient(transport=httpx.MockTransport(responder))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: cliente)
    assert meta.descargar_imagen("42") == (contenido if esperado else None)


def test_peticion_graph_simulada(monkeypatch):
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "token_simulado")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "12345")
    monkeypatch.setenv("WHATSAPP_API_VERSION", "v25.0")
    import json
    def aceptar(req):
        assert str(req.url) == "https://graph.facebook.com/v25.0/12345/messages"
        assert req.headers["Authorization"] == "Bearer token_simulado"
        assert json.loads(req.content)["biz_opaque_callback_data"] == "referencia"
        return httpx.Response(200, json={"messages": [{"id": "wamid.mock"}]})
    cliente = httpx.Client(transport=httpx.MockTransport(aceptar))
    monkeypatch.setattr(httpx, "Client", lambda **kw: cliente)
    assert meta.enviar("123456789", meta.texto("Hola"), "referencia") == "wamid.mock"


@pytest.mark.parametrize("modo", ["expirado", "timeout", "otro_host"])
def test_descarga_error_http_o_host(monkeypatch, modo):
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "simulado")
    destinos = []
    def simular(req):
        destinos.append(req.url.host)
        if req.url.host == "graph.facebook.com":
            url = "https://lookaside.fbsbx.com/fichero" if modo != "otro_host" else "https://example.invalid/fichero"
            return httpx.Response(200, json={"mime_type": "image/jpeg", "url": url})
        if modo == "timeout":
            raise httpx.ReadTimeout("simulado")
        return httpx.Response(404)
    cliente = httpx.AsyncClient(transport=httpx.MockTransport(simular))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: cliente)
    assert meta.descargar_imagen("42") is None
    assert "example.invalid" not in destinos


def test_pendientes_respeta_el_commit(database, monkeypatch):
    from backend.models import Usuario
    with Session(database) as session, session.begin():
        usuario = session.scalar(select(Usuario.id).order_by(Usuario.id))
        nota = Notificacion(usuario_id=usuario, tipo="prueba", mensaje="simulado")
        session.add(nota)
        session.flush()
        nid = nota.id
        # Las semillas tienen destinatarios ficticios y carecen de plantilla.
        monkeypatch.delenv("WHATSAPP_TEMPLATE_PROGRAMACION", raising=False)
        worker.procesar_pendientes(database)
        assert session.get(Notificacion, nid).intentos == 0
    monkeypatch.delenv("WHATSAPP_TEMPLATE_PRUEBA", raising=False)
    assert worker.procesar_pendientes(database) == 1
    with Session(database) as session:
        assert session.get(Notificacion, nid).intentos == 1
        assert session.scalar(select(MensajeWhatsapp.error_envio).where(
            MensajeWhatsapp.notificacion_id == nid)) == "requiere_plantilla"
