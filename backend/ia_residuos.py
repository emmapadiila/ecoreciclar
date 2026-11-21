"""Adaptador síncrono del reconocedor para app.state.analizar_imagen."""

import asyncio
import math
import os

from httpx import AsyncClient, HTTPError, InvalidURL, TimeoutException, URL
from pydantic import BaseModel, Field

from backend.whatsapp_meta import mime_imagen

MAX_IMAGEN = 10 * 1024 * 1024
MAX_RESPUESTA = 128 * 1024
FORMATOS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
CATEGORIAS = {
    "orgánico": "organico", "organico": "organico",
    "reciclable": "reciclable", "aprovechable": "reciclable",
    "otro": "otro", "no_aprovechable": "otro", "no aprovechable": "otro",
}


class Residuo(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    nombre: str = Field(min_length=1, max_length=200)
    material: str | None = Field(default=None, max_length=200)
    categoria: str | None = Field(default=None, max_length=50)
    recomendacion: str | None = Field(default=None, max_length=500)


class Resultado(BaseModel):
    analisis_id: str = Field(min_length=1, max_length=100)
    estado: str
    residuos: list[Residuo] = Field(max_length=100)
    advertencias: list[str] = Field(default_factory=list, max_length=30)


def error(mensaje):
    return {"analisis_id": None, "estado": "error", "residuos": [],
            "advertencias": [mensaje], "resumen": resumen([])}


def resumen(residuos):
    return {
        "total_objetos_detectados": len(residuos),
        "reciclables": sum(item["categoria"] == "reciclable" for item in residuos),
        "organicos": sum(item["categoria"] == "organico" for item in residuos),
        "no_aprovechables": sum(item["categoria"] == "otro" for item in residuos),
        "requiere_revision": bool(residuos),
    }


async def consultar(url, plazo, datos, mime_type, descripcion, referencia):
    campos = {"descripcion": descripcion}
    if referencia is not None:
        campos["referencia"] = referencia
    archivo = ("residuo." + FORMATOS[mime_type], datos, mime_type)
    async with asyncio.timeout(plazo):
        async with AsyncClient(timeout=plazo, follow_redirects=False, trust_env=False) as cliente:
            async with cliente.stream("POST", url, data=campos, files={"imagen": archivo},
                                      headers={"Accept": "application/json"}) as respuesta:
                if respuesta.status_code in (413, 415, 422):
                    return error("La fotografía no se pudo leer o supera los límites admitidos. Prueba otra o continúa por texto.")
                respuesta.raise_for_status()
                contenido = bytearray()
                async for fragmento in respuesta.aiter_bytes(chunk_size=8192):
                    contenido.extend(fragmento)
                    if len(contenido) > MAX_RESPUESTA:
                        raise ValueError("Respuesta de IA demasiado extensa")
                resultado = Resultado.model_validate_json(contenido)
    if resultado.estado != "completado":
        return error("No fue posible analizar la imagen. Puedes continuar por texto.")
    residuos = []
    ids = set()
    for objeto in resultado.residuos:
        if objeto.id in ids:
            raise ValueError("Identificador de objeto repetido")
        ids.add(objeto.id)
        categoria = CATEGORIAS.get((objeto.categoria or "").strip().lower())
        material = objeto.material
        # El reconocedor usa esta etiqueta para el material de botella; el catálogo
        # conversacional reconoce la descripción equivalente «botella plástica».
        if categoria == "reciclable" and (material or "").strip().casefold() == "plástico de botella":
            material = "Botella plástica"
        residuos.append({
            **objeto.model_dump(), "material": material, "categoria": categoria, "requiere_revision": True,
            "colectivo_sugerido": {"organico": "huerta", "reciclable": "recicladores"}.get(categoria),
            "recomendacion": objeto.recomendacion or "Confirma el material antes de solicitar su recogida.",
        })
    return {
        "analisis_id": resultado.analisis_id, "estado": "completado", "residuos": residuos,
        "advertencias": [aviso[:500] for aviso in resultado.advertencias]
        or ([] if residuos else ["No se identificaron residuos con suficiente certeza."]),
        "resumen": resumen(residuos),
    }


def analizar_imagen(
    datos: bytes, mime_type: str, descripcion: str = "", referencia: str | None = None,
) -> dict:
    """Envía una fotografía acotada al reconocedor configurado, sin crear solicitudes."""
    if mime_type not in FORMATOS or not datos or len(datos) > MAX_IMAGEN or mime_imagen(datos) != mime_type:
        return error("Usa una foto JPEG, PNG o WebP válida, de hasta 10 MiB, o continúa por texto.")
    if len(descripcion) > 300 or (referencia is not None and len(referencia) > 100):
        return error("La descripción o la referencia de la imagen supera el límite admitido.")
    try:
        url = URL(os.getenv("ECO_IA_URL", ""))
        plazo = float(os.getenv("ECO_IA_TIMEOUT", "15"))
        if (url.scheme not in ("http", "https") or not url.host or url.userinfo or url.query
                or url.fragment or not math.isfinite(plazo) or not 0 < plazo <= 60):
            return error("El reconocimiento por foto no está disponible. Puedes continuar por texto.")
        return asyncio.run(consultar(url, plazo, datos, mime_type, descripcion, referencia))
    except (TimeoutError, TimeoutException):
        return error("El análisis tardó demasiado. Puedes continuar por texto.")
    except (HTTPError, InvalidURL, ValueError):
        return error("No fue posible analizar la imagen. Puedes continuar por texto.")
