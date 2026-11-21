"""Transporte de OpenWA para una sesión de chats individuales."""
import base64
import os
import re
from urllib.parse import quote

import httpx

from backend import whatsapp_meta as meta


def extraer(payload):
    from backend.whatsapp import MensajeEntrante, _fecha_meta

    sesion = os.getenv("OPENWA_SESSION_ID")
    if not sesion or payload["sessionId"] != sesion or payload["event"] != "message.received":
        return []
    msg = payload["data"]
    if msg["fromMe"] is not False or msg["isGroup"] is not False or msg.get("kind") != "individual":
        return []
    chat = msg["chatId"]
    if chat != msg["from"]:
        return []
    numero, _, dominio = chat.partition("@")
    if dominio == "lid":
        numero = msg.get("senderPhone") or ""
    elif dominio != "c.us":
        return []
    if not re.fullmatch(r"[0-9]{5,15}", numero):
        return []
    if not isinstance(msg["id"], str) or not msg["id"] or len(msg["id"]) > 245:
        raise ValueError("ID inválido")
    tipo = msg["type"]
    texto = msg["body"] if tipo == "text" else None
    if texto is not None and not isinstance(texto, str):
        raise ValueError("Texto inválido")
    evento = MensajeEntrante(numero, "openwa:in:" + msg["id"], tipo, texto=texto,
                             fecha_meta=_fecha_meta(msg["timestamp"]))
    if tipo == "image":
        media = msg.get("media") or {}
        encoded = media.get("data")
        if isinstance(encoded, str) and len(encoded) <= 4 * ((meta.LIMITE + 2) // 3):
            try:
                datos = base64.b64decode(encoded, validate=True)
            except ValueError:
                datos = b""
            mime = meta.mime_imagen(datos)
            if mime and mime == media.get("mimetype") and len(datos) <= meta.LIMITE:
                evento.imagen = datos
    return [evento]


def enviar(numero, texto):
    base = os.getenv("OPENWA_URL", "").rstrip("/")
    sesion = os.getenv("OPENWA_SESSION_ID", "")
    clave = os.getenv("OPENWA_API_KEY")
    if not base or not sesion or not clave or not re.fullmatch(r"[0-9]{5,15}", numero):
        raise meta.ErrorMeta("configuracion_openwa")
    try:
        respuesta = httpx.post(f"{base}/api/sessions/{quote(sesion, safe='')}/messages/send-text",
                               headers={"X-API-Key": clave}, timeout=20,
                               json={"chatId": numero + "@c.us", "text": texto})
        respuesta.raise_for_status()
        mid = respuesta.json()["messageId"]
        if not isinstance(mid, str) or not 0 < len(mid) <= 244:
            raise ValueError
        return "openwa:out:" + mid
    except (httpx.ConnectError, httpx.ConnectTimeout):
        raise meta.ErrorMeta("openwa_sin_conexion", reintentar=True) from None
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        raise meta.ErrorMeta(f"openwa_http_{status}", reintentar=status == 429,
                             incierto=status >= 500 or status == 408) from None
    except (httpx.RequestError, KeyError, TypeError, ValueError):
        raise meta.ErrorMeta("resultado_openwa_desconocido", incierto=True) from None
