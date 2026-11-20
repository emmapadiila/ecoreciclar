"""Webhook de WhatsApp Business Cloud API para EcoConecta 360 (Manuel).

Fases 1-2 del plan, integradas con el contrato de Ángel (docs/arquitectura.md):

- GET  /webhooks/whatsapp: verificación de Meta (hub.challenge, token comparado
  en tiempo constante).
- POST /webhooks/whatsapp: valida la firma X-Hub-Signature-256 (HMAC-SHA256 de
  Meta sobre el cuerpo CRUDO con META_APP_SECRET) y SOLO después de verificarla
  invoca services.register_verified_message, que registra usuario (sin habilitar
  piloto), conversación y mensaje entrante de forma idempotente por
  meta_message_id (T04: los reintentos de Meta no reprocesan).
- El procesamiento conversacional corre en la MISMA transacción de la petición
  (fila, efectos y marca 'procesado' juntos, como pide arquitectura.md). Un
  fallo en un mensaje se aísla con un SAVEPOINT: no aborta la petición ni el
  registro de los demás; el mensaje queda 'pendiente' para el worker de
  reintento (recibir no implica procesar). Es síncrono y no en BackgroundTasks
  por una razón medible: en FastAPI/Starlette las tareas de fondo corren ANTES
  del commit de la dependencia de sesión, y verían la fila sin confirmar.
- Cada respuesta del bot queda auditada en mensajes_whatsapp con
  direccion='saliente'; su estado_envio refleja el resultado real de la llamada
  a Meta (sin credenciales: 'fallido'; nunca se finge un envío).

Montaje en backend/main.py (coordinar con Breiner, no editar por nuestra cuenta):
    from backend.whatsapp import router as whatsapp_router
    app.include_router(whatsapp_router)

URL de callback en Meta: {dominio}/webhooks/whatsapp
Variables de entorno (documentar nombres en .env.example del PR):
    WHATSAPP_VERIFY_TOKEN, META_APP_SECRET, WHATSAPP_ACCESS_TOKEN,
    WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_API_VERSION
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend import services
from backend.db import get_session
from backend.models import Conversacion, MensajeWhatsapp, Usuario

logger = logging.getLogger("ecoreciclar.whatsapp")

router = APIRouter(prefix="/webhooks", tags=["whatsapp"])

DB = Annotated[Session, Depends(get_session)]

MENSAJE_MENU = (
    "Hola, soy el asistente de EcoConecta 360 en Villas de San Pablo.\n"
    "Escribe el número de la opción que necesitas:\n"
    "1. Agendar una recolección a domicilio\n"
    "2. Consultar mis solicitudes\n"
    "3. Consultar mis EcoPuntos\n"
    "4. Consejos para separar residuos"
)

RESPUESTA_FOTO = (
    "Recibí tu foto. La clasificación con IA todavía no está activa en el piloto; "
    "pronto te propondré categoría y colectivo. Mientras tanto puedes escribir 1 "
    "para agendar una recolección."
)

SALUDOS = {"hola", "buenas", "menu", "menú", "inicio"}

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


# ----------------------------- seguridad ------------------------------------


def verificar_firma(cuerpo: bytes, firma_recibida: str | None) -> bool:
    """Compara X-Hub-Signature-256 con el HMAC-SHA256 del cuerpo crudo.

    Sin META_APP_SECRET configurado se rechaza todo (fail closed).
    """
    secreto = os.getenv("META_APP_SECRET", "")
    if not secreto:
        logger.warning(
            "META_APP_SECRET sin configurar: evento rechazado (fail closed)."
        )
        return False
    esperada = (
        "sha256="
        + hmac.new(secreto.encode("utf-8"), cuerpo, hashlib.sha256).hexdigest()
    )
    return hmac.compare_digest(esperada, firma_recibida or "")


# ----------------------------- parser ----------------------------------------


def extraer_mensajes(payload: dict) -> list[MensajeEntrante]:
    """Extrae los mensajes de usuario de un payload de webhook de Meta.

    Los recibos de estado (sent/delivered/read) no traen la clave 'messages'
    y por tanto se ignoran silenciosamente.
    """
    mensajes: list[MensajeEntrante] = []
    for entrada in payload.get("entry", []):
        for cambio in entrada.get("changes", []):
            if cambio.get("field") != "messages":
                continue
            for crudo in cambio.get("value", {}).get("messages", []):
                interactivo = (crudo.get("interactive") or {}).get("button_reply") or {}
                boton = crudo.get("button") or {}
                mensajes.append(
                    MensajeEntrante(
                        wa_id=crudo.get("from", ""),
                        mensaje_id=crudo.get("id", ""),
                        tipo=crudo.get("type", "otros"),
                        texto=(crudo.get("text") or {}).get("body"),
                        media_id=(crudo.get("image") or {}).get("id"),
                        mime_type=(crudo.get("image") or {}).get("mime_type"),
                        titulo_boton=interactivo.get("title") or boton.get("text"),
                    )
                )
    return mensajes


# --------------------- envío hacia Meta (Fase 2; foto en Fase 6) --------------


def enviar_texto(wa_id: str, texto: str) -> str | None:
    """Envía texto vía Graph API y devuelve el id de Meta, o None si no se pudo.

    Un fallo de envío NO lanza excepción hacia el flujo conversacional: se
    registra en el log y devuelve None (T27: el envío fallido no pierde la
    solicitud). Sin credenciales degrada con aviso claro (modo local sin Meta).
    """
    import httpx

    token = os.getenv("WHATSAPP_ACCESS_TOKEN") or None
    telefono_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID") or None
    version = os.getenv("WHATSAPP_API_VERSION") or "v22.0"
    if not token or not telefono_id:
        logger.warning(
            "Credenciales de WhatsApp sin configurar; no se envía mensaje a %s "
            "(modo local sin Meta).",
            wa_id,
        )
        return None
    url = f"https://graph.facebook.com/{version}/{telefono_id}/messages"
    carga = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": wa_id,
        "type": "text",
        "text": {"preview_url": False, "body": texto},
    }
    try:
        with httpx.Client(timeout=15) as cliente:
            respuesta = cliente.post(
                url, headers={"Authorization": f"Bearer {token}"}, json=carga
            )
            respuesta.raise_for_status()
            datos = respuesta.json()
        mensajes = datos.get("messages") or [{}]
        return mensajes[0].get("id")
    except Exception as error:  # noqa: BLE001 - el bot nunca debe caer por un envío
        logger.error("Fallo enviando texto a %s: %s", wa_id, error)
        return None


def descargar_imagen(media_id: str) -> bytes | None:
    """Descarga una imagen por su media_id (se conecta en la Fase 6, IA).

    Valida MIME (jpeg/png/webp) y un máximo de 5 MB. Devuelve None ante
    cualquier problema; nunca lanza hacia el flujo conversacional.
    """
    import httpx

    token = os.getenv("WHATSAPP_ACCESS_TOKEN") or None
    version = os.getenv("WHATSAPP_API_VERSION") or "v22.0"
    if not token:
        logger.warning(
            "WHATSAPP_ACCESS_TOKEN sin configurar; no se baja la imagen %s.", media_id
        )
        return None
    try:
        with httpx.Client(timeout=30) as cliente:
            info_resp = cliente.get(
                f"https://graph.facebook.com/{version}/{media_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            info_resp.raise_for_status()
            info = info_resp.json()
            if info.get("mime_type") not in {"image/jpeg", "image/png", "image/webp"}:
                logger.warning(
                    "MIME no aceptado (%s) para la imagen %s.",
                    info.get("mime_type"),
                    media_id,
                )
                return None
            if int(info.get("file_size") or 0) > 5 * 1024 * 1024:
                logger.warning("Imagen %s supera 5 MB; se rechaza.", media_id)
                return None
            archivo = cliente.get(
                info["url"], headers={"Authorization": f"Bearer {token}"}
            )
            archivo.raise_for_status()
            return archivo.content
    except Exception as error:  # noqa: BLE001
        logger.error("Fallo descargando la imagen %s: %s", media_id, error)
        return None


# --------------------- respuestas de la Fase 2 -------------------------------
# La Fase 3 (conversacion.py) leerá conversacion.estado_actual y
# conversacion.datos_temporales para el estado máquina real; este bloque es el
# punto único donde se decide la respuesta.


def responder_texto(texto: str | None) -> str:
    """T03: el saludo devuelve el menú; de momento cualquier otro texto también."""
    normalizado = (texto or "").strip().lower()
    if normalizado in SALUDOS or normalizado.startswith("hola"):
        return MENSAJE_MENU
    return "No reconocí esa opción.\n\n" + MENSAJE_MENU


def responder(
    mensaje: MensajeWhatsapp, conversacion: Conversacion, usuario: Usuario
) -> str:
    """Decide la respuesta según el tipo de mensaje entrante (Fase 2).

    Fase 3: añadir la verificación usuario.piloto_habilitado antes de agendar
    (los remitentes nuevos se registran sin habilitar el piloto) y el ciclo
    completo del estado máquina.
    """
    if mensaje.tipo == "imagen":
        return RESPUESTA_FOTO
    if mensaje.tipo == "respuesta":
        return (
            f"Anoté tu opción: {mensaje.contenido or 'sin título'}. "
            "Este flujo se conectará durante el piloto.\n\n" + MENSAJE_MENU
        )
    return responder_texto(mensaje.contenido)


# --------------------- procesamiento en la transacción ------------------------


def procesar_mensaje(
    session: Session, mensaje: MensajeWhatsapp, usuario: Usuario
) -> None:
    """Ejecuta los efectos de un mensaje registrado, en la transacción en curso.

    Según docs/arquitectura.md: registrar, ejecutar efectos y marcar
    'procesado' quedan en una sola transacción. El llamador envuelve esta
    función en un SAVEPOINT: si algo falla, se revierte solo este mensaje y la
    fila queda 'pendiente' para el worker de reintento (recibir no implica
    procesar; un error transitorio nunca se marca como 'fallido').
    """
    conversacion = session.get(Conversacion, mensaje.conversacion_id)
    respuesta = responder(mensaje, conversacion, usuario)
    id_meta_salida = enviar_texto(usuario.whatsapp_id or "", respuesta)
    session.add(
        MensajeWhatsapp(
            conversacion_id=conversacion.id,
            meta_message_id=id_meta_salida or f"saliente-sin-entrega-{uuid4().hex}",
            direccion="saliente",
            tipo="texto",
            contenido=respuesta,
            estado_envio="enviado" if id_meta_salida else "fallido",
        )
    )
    mensaje.estado_procesamiento = "procesado"
    conversacion.fecha_actualizacion = datetime.now(timezone.utc)
    session.flush()


# ----------------------------- endpoints -------------------------------------


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
        and hmac.compare_digest(hub_verify_token, esperado)
    ):
        return PlainTextResponse(content=hub_challenge, status_code=200)
    return JSONResponse(status_code=403, content={"detail": "Verificación rechazada"})


@router.post("/whatsapp")
async def recibir_eventos(request: Request, session: DB):
    """Recibe eventos firmados de Meta y procesa cada mensaje con SAVEPOINT.

    La deduplicación real es la unicidad de meta_message_id en la base,
    garantizada por services.register_verified_message (probada por Ángel con
    concurrencia en test_concurrent_message_delivery).
    """
    cuerpo = await request.body()
    if not verificar_firma(cuerpo, request.headers.get("X-Hub-Signature-256")):
        return JSONResponse(status_code=403, content={"detail": "Firma inválida"})
    try:
        payload = json.loads(cuerpo)
    except json.JSONDecodeError:
        return JSONResponse(status_code=400, content={"detail": "JSON inválido"})
    if not isinstance(payload, dict):
        return JSONResponse(status_code=400, content={"detail": "JSON inválido"})

    nuevos = 0
    for evento in extraer_mensajes(payload):
        if not evento.mensaje_id or not evento.wa_id:
            continue
        try:
            usuario, mensaje, creado = services.register_verified_message(
                session,
                evento.wa_id,
                evento.mensaje_id,
                TIPOS.get(evento.tipo, "otros"),
            )
        except ValueError as error:
            # p. ej. meta_message_id ya vinculado a otra identidad: se rechaza
            # este mensaje y se aceptan los demás del mismo lote.
            logger.warning("Mensaje %s rechazado: %s", evento.mensaje_id, error)
            continue
        if not creado:
            continue  # T04: reintentos de Meta no reprocesan
        # Contenido mínimo para contexto conversacional; None para imágenes.
        mensaje.contenido = evento.texto or evento.titulo_boton
        session.flush()
        try:
            with session.begin_nested():  # SAVEPOINT: aísla el fallo de este mensaje
                procesar_mensaje(session, mensaje, usuario)
        except Exception:  # noqa: BLE001
            logger.exception(
                "Fallo procesando %s; queda pendiente para reintento del worker",
                evento.mensaje_id,
            )
        nuevos += 1
    return {"success": True, "nuevos": nuevos}
