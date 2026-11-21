"""Transporte HTTP. Los errores de auditoría nunca incluyen cabeceras ni cuerpos."""
import asyncio
import os
import re

import httpx

LIMITE = 5 * 1024 * 1024
VERSION = "v25.0"


class ErrorMeta(Exception):
    def __init__(self, causa, *, reintentar=False, incierto=False):
        super().__init__(causa)
        self.reintentar = reintentar
        self.incierto = incierto


def _conexion():
    token = os.getenv("WHATSAPP_ACCESS_TOKEN")
    version = os.getenv("WHATSAPP_API_VERSION") or VERSION
    if not token or not re.fullmatch(r"v[1-9][0-9]*\.0", version):
        raise ErrorMeta("configuracion")
    return f"https://graph.facebook.com/{version}", {"Authorization": f"Bearer {token}"}


def enviar(wa_id, contenido, referencia=None):
    base, headers = _conexion()
    telefono = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    if not re.fullmatch(r"[0-9]+", telefono) or not re.fullmatch(r"[0-9]{5,15}", wa_id):
        raise ErrorMeta("telefono_invalido")
    carga = {"messaging_product": "whatsapp", "to": wa_id, **contenido}
    if referencia:
        carga["biz_opaque_callback_data"] = referencia
    try:
        with httpx.Client(timeout=15) as cliente:
            respuesta = cliente.post(f"{base}/{telefono}/messages", headers=headers, json=carga)
        if respuesta.status_code == 429:
            raise ErrorMeta("limite_meta", reintentar=True)
        respuesta.raise_for_status()
        wamid = respuesta.json()["messages"][0]["id"]
        if not isinstance(wamid, str) or not 0 < len(wamid) <= 255:
            raise ValueError
        return wamid
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout):
        raise ErrorMeta("sin_conexion", reintentar=True) from None
    except httpx.HTTPStatusError as error:
        codigo = error.response.status_code
        raise ErrorMeta(f"http_{codigo}", incierto=codigo >= 500 or codigo == 408) from None
    except (httpx.RequestError, IndexError, KeyError, TypeError, ValueError):
        raise ErrorMeta("resultado_desconocido", incierto=True) from None


def texto(body):
    return {"type": "text", "text": {"preview_url": False, "body": body}}


def mime_imagen(datos):
    if datos.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if datos.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if datos[:4] == b"RIFF" and datos[8:12] == b"WEBP":
        return "image/webp"
    return None


def descargar_imagen(media_id: str) -> bytes | None:
    """Interfaz síncrona utilizada por el worker fuera del bucle de FastAPI."""
    return asyncio.run(_descargar(media_id))


async def _descargar(media_id):
    if not re.fullmatch(r"[0-9]+", media_id):
        return None
    try:
        base, headers = _conexion()
        async with asyncio.timeout(30), httpx.AsyncClient(timeout=5, follow_redirects=False) as cliente:
            respuesta = await cliente.get(f"{base}/{media_id}", headers=headers)
            respuesta.raise_for_status()
            info = respuesta.json()
            mime = info["mime_type"]
            if mime not in {"image/jpeg", "image/png", "image/webp"}:
                return None
            if int(info.get("file_size", 0)) > LIMITE:
                return None
            url = httpx.URL(info["url"])
            if url.scheme != "https" or url.host != "lookaside.fbsbx.com" or url.userinfo or url.port:
                return None
            async with cliente.stream("GET", url, headers=headers) as archivo:
                archivo.raise_for_status()
                if archivo.headers.get("Content-Type", "").split(";")[0].lower() != mime:
                    return None
                datos = bytearray()
                async for bloque in archivo.aiter_bytes():
                    if len(datos) + len(bloque) > LIMITE:
                        return None
                    datos.extend(bloque)
                if mime_imagen(datos) == mime:
                    return bytes(datos)
    except (TimeoutError, ErrorMeta, httpx.HTTPError, httpx.InvalidURL, KeyError, TypeError, ValueError):
        pass
    return None
