"""Webhook firmado de EcoConecta y adaptador conversacional de WhatsApp."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from backend import services, whatsapp_openwa
from backend.db import engine
from backend import notificaciones_whatsapp as outbox, whatsapp_meta as meta
from backend.whatsapp_meta import descargar_imagen
from backend.models import Conversacion, MensajeWhatsapp, Notificacion, Usuario

logger = logging.getLogger("ecoreciclar.whatsapp")

router = APIRouter(prefix="/webhooks", tags=["whatsapp"])

# Tipo de Meta -> tipo interno según el comentario de MensajeWhatsapp.tipo.
TIPOS = {
    "text": "texto",
    "image": "imagen",
    "interactive": "respuesta",
    "button": "respuesta",
}


@dataclass
class MensajeEntrante:
    """Mensaje entrante ya extraído del payload de Meta."""

    wa_id: str
    mensaje_id: str
    tipo: str
    texto: str | None = None
    media_id: str | None = None
    mime_type: str | None = None
    titulo_boton: str | None = None
    fecha_meta: datetime | None = None
    imagen: bytes | None = field(default=None, repr=False)
    analisis_imagen: object = field(default=None, repr=False)


# ----------------------------- seguridad ------------------------------------


def verificar_firma(cuerpo: bytes, firma_recibida: str | None, variable="META_APP_SECRET") -> bool:
    """Compara X-Hub-Signature-256 con el HMAC-SHA256 del cuerpo crudo.

    Sin META_APP_SECRET configurado se rechaza todo (fail closed).
    """
    secreto = os.getenv(variable, "")
    if not secreto:
        logger.warning(
            "%s sin configurar: evento rechazado.", variable
        )
        return False
    esperada = (
        "sha256="
        + hmac.new(secreto.encode("utf-8"), cuerpo, hashlib.sha256).hexdigest()
    )
    return hmac.compare_digest(esperada.encode(), (firma_recibida or "").encode())


# ----------------------------- parser ----------------------------------------


def _lista(objeto, clave):
    valor = objeto.get(clave, [])
    if not isinstance(valor, list) or any(not isinstance(x, dict) for x in valor):
        raise ValueError("Lista inválida")
    return valor


def _valores(payload):
    for entrada in _lista(payload, "entry"):
        for cambio in _lista(entrada, "changes"):
            if cambio.get("field") == "messages":
                valor = cambio["value"]
                telefono = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
                if not telefono or valor.get("metadata", {}).get("phone_number_id") == telefono:
                    yield valor


def _fecha_meta(valor):
    if valor is None:
        return None
    fecha = datetime.fromtimestamp(int(valor), timezone.utc)
    return min(fecha, datetime.now(timezone.utc))


def extraer_mensajes(payload: dict) -> list[MensajeEntrante]:
    """Extrae mensajes de usuario del número configurado."""
    mensajes = []
    for valor in _valores(payload):
        for crudo in _lista(valor, "messages"):
            interactivo = (crudo.get("interactive") or {}).get("button_reply") or {}
            boton = crudo.get("button") or {}
            mensajes.append(
                MensajeEntrante(
                    wa_id=crudo.get("from", ""),
                    mensaje_id=crudo.get("id", ""),
                    tipo=crudo.get("type", "otros"),
                    fecha_meta=_fecha_meta(crudo.get("timestamp")),
                    texto=(crudo.get("text") or {}).get("body"),
                    media_id=(crudo.get("image") or {}).get("id"),
                    mime_type=(crudo.get("image") or {}).get("mime_type"),
                    titulo_boton=interactivo.get("title") or boton.get("text"),
                )
            )
    return mensajes


# --------------------- envío hacia Meta (Fase 2; foto en Fase 6) --------------


def enviar_texto(wa_id: str, texto: str) -> str | None:
    """Interfaz compatible para los consumidores del transporte."""
    try:
        return meta.enviar(wa_id, meta.texto(texto))
    except meta.ErrorMeta as error:
        logger.warning("Fallo de envío: %s", error)
        return None


def procesar_mensaje(session, mensaje, usuario, evento, chatbot):
    conversacion = session.get(Conversacion, mensaje.conversacion_id, with_for_update=True)
    respuestas = chatbot(session, usuario, conversacion, evento)
    if not isinstance(respuestas, list) or any(not isinstance(r, str) or not r for r in respuestas):
        raise ValueError("Respuesta del chatbot inválida")
    notas = [Notificacion(usuario_id=usuario.id, tipo="respuesta", mensaje=r) for r in respuestas]
    session.add_all(notas)
    mensaje.estado_procesamiento = "procesado"
    conversacion.fecha_actualizacion = datetime.now(timezone.utc)
    session.flush()
    return [n.id for n in notas]


@router.get("/whatsapp")
def verificar_webhook(
    hub_mode: str = Query(default="", alias="hub.mode"),
    hub_verify_token: str = Query(default="", alias="hub.verify_token"),
    hub_challenge: str = Query(default="", alias="hub.challenge"),
):
    """Verificación de Meta: eco del challenge solo con el token correcto."""
    esperado = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
    if (
        hub_mode == "subscribe"
        and esperado
        and hub_challenge
        and hmac.compare_digest(hub_verify_token.encode(), esperado.encode())
    ):
        return PlainTextResponse(content=hub_challenge, status_code=200)
    return JSONResponse(status_code=403, content={"detail": "Verificación rechazada"})


def _procesar_registrado(bind, mid, uid, evento, chatbot, analizar):
    with bind.connect() as conexion:
        # Un análisis puede tardar más que el reintento del webhook. Este bloqueo
        # de sesión sobre el id interno sobrevive al commit durante la E/S.
        llave = {"id": -mid}
        with conexion.begin():
            if not conexion.scalar(text("SELECT pg_try_advisory_lock(:id)"), llave):
                raise RuntimeError("Evento en curso")
        try:
            with Session(conexion) as sesion:
                if sesion.get(MensajeWhatsapp, mid).estado_procesamiento == "procesado":
                    return []
            if evento.tipo == "image" and analizar:
                datos = evento.imagen
                if datos is None and evento.media_id:
                    datos = descargar_imagen(evento.media_id)
                if datos is not None:
                    evento.analisis_imagen = analizar(datos, meta.mime_imagen(datos))
            with Session(conexion) as sesion, sesion.begin():
                usuario = sesion.get(Usuario, uid, with_for_update=True)
                mensaje = sesion.get(MensajeWhatsapp, mid, with_for_update=True)
                if usuario.whatsapp_id != evento.wa_id:
                    mensaje.estado_procesamiento = "procesado"
                    return []
                return procesar_mensaje(sesion, mensaje, usuario, evento, chatbot)
        finally:
            try:
                with conexion.begin():
                    conexion.execute(text("SELECT pg_advisory_unlock(:id)"), llave)
            except Exception:
                conexion.invalidate()
                raise


def _procesar_lote(bind, eventos, recibos, chatbot, analizar):
    nuevos = 0
    pendiente = False
    with Session(bind) as session, session.begin():
        for recibo in recibos:
            outbox.registrar_estado(session, recibo)
    for evento in eventos:
        if not evento.mensaje_id or not evento.wa_id:
            continue
        with Session(bind) as session, session.begin():
            try:
                usuario, mensaje, creado = services.register_verified_message(
                    session, evento.wa_id, evento.mensaje_id, TIPOS.get(evento.tipo, "otros"))
            except ValueError:
                logger.warning("Identidad de mensaje rechazada")
                continue
            if mensaje.direccion != "entrante" or mensaje.estado_procesamiento == "procesado":
                continue
            if creado:
                mensaje.contenido = evento.texto or evento.titulo_boton
                mensaje.fecha_meta = evento.fecha_meta
                nuevos += 1
            mid, uid = mensaje.id, usuario.id
        try:
            notas = _procesar_registrado(bind, mid, uid, evento, chatbot, analizar)
            for nota_id in notas:
                outbox.despachar(bind, nota_id)
        except Exception:
            pendiente = True
    if pendiente:
        raise RuntimeError("Lote con eventos pendientes")
    return nuevos


@router.post("/whatsapp")
async def recibir_eventos(request: Request):
    if os.getenv("WHATSAPP_PROVIDER", "meta") != "meta":
        return JSONResponse(status_code=404, content={"detail": "Proveedor inactivo"})
    cuerpo = await request.body()
    if not verificar_firma(cuerpo, request.headers.get("X-Hub-Signature-256")):
        return JSONResponse(status_code=403, content={"detail": "Firma inválida"})
    try:
        payload = json.loads(cuerpo)
        if not isinstance(payload, dict) or "entry" not in payload:
            raise ValueError
        eventos = extraer_mensajes(payload)
        recibos = [r for v in _valores(payload) for r in _lista(v, "statuses")]
        for r in recibos:
            if not all(isinstance(r.get(k, ""), str) for k in ("id", "status", "biz_opaque_callback_data")):
                raise ValueError
        for e in eventos:
            if not all(isinstance(x, str) for x in (e.wa_id, e.mensaje_id, e.tipo)):
                raise ValueError
            if len(e.wa_id) > 64 or len(e.mensaje_id) > 255 or any(
                x is not None and not isinstance(x, str) for x in (e.texto, e.media_id, e.mime_type, e.titulo_boton)
            ):
                raise ValueError
    except (ValueError, TypeError, AttributeError, KeyError, OverflowError, OSError):
        return JSONResponse(status_code=400, content={"detail": "Evento inválido"})
    return await procesar_entrega(request, eventos, recibos)


@router.post("/openwa")
async def recibir_openwa(request: Request):
    if os.getenv("WHATSAPP_PROVIDER") != "openwa":
        return JSONResponse(status_code=404, content={"detail": "Proveedor inactivo"})
    cuerpo = bytearray()
    async for parte in request.stream():
        if len(cuerpo) + len(parte) > 8 * 1024 * 1024:
            return JSONResponse(status_code=413, content={"detail": "Evento demasiado grande"})
        cuerpo.extend(parte)
    if not verificar_firma(cuerpo, request.headers.get("X-OpenWA-Signature"), "OPENWA_WEBHOOK_SECRET"):
        return JSONResponse(status_code=403, content={"detail": "Firma inválida"})
    try:
        eventos = whatsapp_openwa.extraer(json.loads(cuerpo))
    except (ValueError, TypeError, AttributeError, KeyError, OverflowError, OSError):
        return JSONResponse(status_code=400, content={"detail": "Evento inválido"})
    if not eventos:
        return {"success": True, "nuevos": 0}
    return await procesar_entrega(request, eventos, [])


async def procesar_entrega(request, eventos, recibos):
    try:
        nuevos = await run_in_threadpool(
            _procesar_lote, engine(), eventos, recibos,
            request.app.state.procesar_evento,
            getattr(request.app.state, "analizar_imagen", None))
    except Exception:
        logger.error("Procesamiento pendiente de reintento")
        return JSONResponse(status_code=503, content={"detail": "Reintentar evento"})
    return {"success": True, "nuevos": nuevos}
