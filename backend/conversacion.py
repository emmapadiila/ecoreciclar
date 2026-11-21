"""Máquina de estados del chatbot. El webhook conserva la transacción y el envío."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from typing import TYPE_CHECKING
import unicodedata
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend import registro_whatsapp as registro, services
from backend.models import Asignacion, Colectivo, Conversacion, Material, MovimientoPuntos, Solicitud, Usuario

if TYPE_CHECKING:
    from backend.whatsapp import MensajeEntrante


MENU = (
    "EcoConecta 360 ♻️\n¿Qué deseas hacer?\n1. Solicitar recolección\n"
    "2. Consultar mis solicitudes\n3. Consultar mis EcoPuntos\n"
    "4. Consejos para separar residuos\n5. Actualizar mis datos"
)
TIPOS = "¿Qué tipo de residuos deseas entregar?\n1. Orgánicos · 2. Reciclables · 3. No estoy seguro."
METODO = "1. Enviar una fotografía · 2. Escribir los materiales que tienes."
CONSEJOS = "Separa los orgánicos. Entrega reciclables limpios y secos. Si tienes dudas, consulta el catálogo del piloto."
CATEGORIAS = {"organico": "Orgánico", "reciclable": "Reciclable"}
ESTADOS = {"recibida": "Recibida", "en_revision": "En revisión", "asignada": "Asignada",
           "programada": "Programada", "recolectada": "Cerrada", "cancelada": "Cancelada"}
ALIAS = {
    "pet": ("botella plastica", "botella de plastico", "botella pet"),
    "vegetal": ("resto de verdura", "resto vegetal", "cascara de fruta", "residuo vegetal"),
}
CAPTURA = {"materiales", "metodo", "espera_imagen", "revision_material", "direccion",
           "direccion_nueva", "horario", "observaciones", "confirmacion", "editar"}
CAPTURA_FOTO = {"tipo", "metodo", "espera_imagen", "materiales"}
CADUCIDAD = timedelta(hours=24)


def resumen_foto(analisis):
    if not analisis or analisis["estado"] != "completado":
        return "No pude analizar la foto. Puedes reenviarla o describir el residuo por texto."

    residuos = analisis["residuos"]
    lineas = []
    for categoria, etiqueta in (("organico", "orgánico"), ("reciclable", "aprovechable")):
        grupo = [item for item in residuos if item["categoria"] == categoria]
        if grupo:
            materiales = list(dict.fromkeys(item["material"] for item in grupo if item.get("material")))
            detalle = f" ({', '.join(materiales[:5])})" if materiales else ""
            lineas.append(f"• {len(grupo)} de tipo {etiqueta}{detalle}")
    mensaje = "En la foto parece haber:\n" + "\n".join(lineas) if lineas else ""
    if not lineas:
        return "No pude identificar el residuo con claridad. Envía otra foto o describe el material por texto."
    if any(item["categoria"] not in CATEGORIAS for item in residuos):
        return mensaje + "\nHay objetos dudosos. Envía otra foto o describe el material por texto."
    return mensaje


class MaterialConfirmado(BaseModel):
    material_id: int = Field(gt=0)
    confirmado: bool = True


class SolicitudConfirmada(BaseModel):
    direccion: str = Field(min_length=1, max_length=1000)
    descripcion: str | None = Field(default=None, max_length=2000)
    horario_preferido: str = Field(min_length=1, max_length=500)
    materiales: list[MaterialConfirmado] = Field(min_length=1, max_length=30)


def normalizar(texto):
    ascii_text = "".join(c for c in unicodedata.normalize("NFD", texto.casefold())
                         if not unicodedata.combining(c))
    return " ".join(re.findall(r"[a-z0-9]+", ascii_text))


def frase(texto):
    palabras = normalizar(texto).split()
    return " ".join(palabra[:-2] if palabra.endswith("ales") else
                    palabra[:-1] if len(palabra) > 3 and palabra.endswith("s") else palabra
                    for palabra in palabras)


def catalogo(session):
    return list(session.scalars(select(Material).where(
        Material.activo, Material.aceptado, Material.categoria.in_(CATEGORIAS),
    ).order_by(Material.nombre, Material.id)))


def coincidencias(texto, materiales):
    consulta = " " + frase(texto) + " "
    hallados = []
    for material in materiales:
        nombre = frase(material.nombre).removeprefix("demo ")
        etiquetas = [nombre]
        for clave, sinonimos in ALIAS.items():
            if clave in nombre.split():
                etiquetas += [clave, *sinonimos]
        if any(etiqueta and f" {frase(etiqueta)} " in consulta for etiqueta in etiquetas):
            hallados.append(material)
    return hallados


def materiales_ia(resultado, materiales):
    if not isinstance(resultado, dict) or resultado.get("estado") != "completado":
        return [], False
    residuos = resultado.get("residuos")
    if not isinstance(residuos, list) or not residuos or len(residuos) > 100:
        return [], False
    ids = set()
    incompleto = False
    for residuo in residuos:
        if not isinstance(residuo, dict) or residuo.get("categoria") not in tuple(CATEGORIAS):
            incompleto = True
            continue
        candidatos = [material for material in materiales if material.categoria == residuo["categoria"]]
        for campo in ("material", "nombre"):
            valor = residuo.get(campo)
            if isinstance(valor, str) and 0 < len(valor) <= 200:
                matches = coincidencias(valor, candidatos)
                if len(matches) == 1:
                    ids.add(matches[0].id)
                    break
        else:
            incompleto = True
    return [material for material in materiales if material.id in ids], incompleto


def consultar(session, usuario, opcion):
    if opcion == "3":
        saldo = session.scalar(select(func.coalesce(func.sum(MovimientoPuntos.puntos), 0))
                               .where(MovimientoPuntos.usuario_id == usuario.id))
        return f"Tus EcoPuntos ♻️\nSaldo acumulado: {saldo} puntos. Se acreditan después del pesaje y el cierre."
    filas = session.execute(services.scoped_requests(usuario)
        .add_columns(Colectivo.tipo_flujo, Asignacion.programada_en)
        .join(Colectivo, Colectivo.id == Solicitud.colectivo_id)
        .outerjoin(Asignacion, Asignacion.solicitud_id == Solicitud.id)
        .order_by(Solicitud.fecha_creacion.desc(), Solicitud.id.desc()).limit(5))
    bogota = ZoneInfo("America/Bogota")
    lineas = []
    for item, categoria, programada in filas:
        linea = f"{item.codigo} — {CATEGORIAS[categoria]} · {ESTADOS[item.estado]} · {item.fecha_creacion.astimezone(bogota):%d/%m/%Y}"
        if programada and item.estado == "programada":
            linea += f" · Programación {programada.astimezone(bogota):%d/%m %H:%M} (Barranquilla)"
        lineas.append(linea)
    return "Tus solicitudes recientes\n" + "\n".join(lineas) if lineas else "Aún no tienes solicitudes."


def opcion_menu(opcion):
    if opcion in ("1", "solicitar", "solicitar recoleccion") or opcion.startswith(("tengo ", "quiero solicitar ")):
        return "1"
    if opcion in ("2", "mis solicitudes", "consultar solicitudes", "consultar mis solicitudes", "estado de mi solicitud"):
        return "2"
    if opcion in ("3", "mis puntos", "ecopuntos", "mis ecopuntos", "consultar mis puntos", "consultar mis ecopuntos"):
        return "3"
    if opcion in ("4", "consejos", "consejos para separar residuos"):
        return "4"
    if opcion in ("5", "actualizar", "actualizar datos", "actualizar mis datos", "cambiar direccion"):
        return "5"
    return None


def procesar_evento(session: Session, usuario: Usuario, conversacion: Conversacion,
                    evento: MensajeEntrante) -> list[str]:
    """Procesa una entrega normalizada dentro del bloqueo y transacción del transporte."""
    if usuario.whatsapp_id != evento.wa_id or conversacion.usuario_id != usuario.id:
        raise ValueError("La identidad no coincide con la conversación")
    ahora = datetime.now(timezone.utc)
    estado = conversacion.estado_actual
    datos = dict(conversacion.datos_temporales)
    vence = datos.pop("_vence", 0)
    expirado = estado not in ("inicio", "menu") and vence <= ahora.timestamp()
    if expirado:
        estado, datos = "inicio", {}

    def responder(nuevo, borrador, *mensajes):
        conversacion.estado_actual = nuevo
        conversacion.datos_temporales = (
            {**borrador, "_vence": (ahora + CADUCIDAD).timestamp()}
            if nuevo not in ("inicio", "menu") else {}
        )
        # El transporte admite un mensaje de texto de hasta 4096 caracteres.
        return [mensaje[i:i + 3500] for mensaje in mensajes for i in range(0, len(mensaje), 3500)]

    texto = " ".join((evento.texto or evento.titulo_boton or "").split())
    opcion = normalizar(texto) if len(texto) <= 2000 else ""
    if not usuario.activo or usuario.rol != "residente":
        return responder("inicio", {}, "Esta cuenta no está habilitada para usar el asistente de residentes.")
    foto = evento.tipo in ("image", "imagen")
    analisis = getattr(evento, "analisis_imagen", None)
    if foto and (estado not in CAPTURA_FOTO or not registro.registrado(usuario) or not usuario.piloto_habilitado):
        mensaje = resumen_foto(analisis)
        if estado in ("inicio", "menu"):
            mensaje += "\nEscribe «Hola» para usar el asistente."
        return responder(estado, datos, mensaje)
    cancelar = opcion in ("cancelar", "cancelar solicitud", "cancelar registro") or (
        opcion == "3" and estado in ("revision_material", "confirmacion", "registro_confirmacion"))
    if cancelar or opcion in ("menu", "volver al menu", "inicio"):
        mensaje = "Borrador cancelado." if cancelar else "Volviste al menú."
        if not registro.registrado(usuario):
            return responder("inicio", {}, mensaje, "Escribe «Hola» para iniciar tu registro.")
        return responder("menu", {}, mensaje, MENU)
    if expirado and opcion not in ("hola", "buenas", "buenos dias", "buenas tardes"):
        return responder("inicio", {}, "Tu borrador venció. Escribe «Hola» para empezar de nuevo.")

    if not registro.registrado(usuario):
        if estado in (*registro.PREGUNTAS, "registro_confirmacion"):
            nuevo, borrador, mensaje = registro.avanzar(usuario, estado, datos, texto, opcion)
            if nuevo == "menu":
                return responder("menu", {}, mensaje, MENU if usuario.piloto_habilitado else registro.SIN_AUTORIZACION)
            return responder(nuevo, borrador, mensaje)
        return responder("registro_nombre", {}, registro.BIENVENIDA, registro.PREGUNTAS["registro_nombre"])

    if not usuario.piloto_habilitado and estado in CAPTURA | {"tipo"}:
        return responder("menu", {}, registro.SIN_AUTORIZACION, MENU)
    if estado in ("inicio", "menu"):
        if opcion in ("hola", "buenas", "buenos dias", "buenas tardes", "buenas noches"):
            bienvenida = f"¡Hola de nuevo, {usuario.nombre}! Encontré tu registro."
            return responder("menu", {}, bienvenida, MENU) if usuario.piloto_habilitado else responder(
                "menu", {}, bienvenida, registro.SIN_AUTORIZACION, MENU)
        elegida = opcion_menu(opcion)
        if elegida in ("1", "2", "3") and not usuario.piloto_habilitado:
            return responder("menu", {}, registro.SIN_AUTORIZACION, MENU)
        if elegida == "1":
            if not opcion.startswith("tengo "):
                return responder("tipo", {}, TIPOS)
            estado = "materiales"
        elif elegida in ("2", "3"):
            return responder("menu", {}, consultar(session, usuario, elegida), MENU)
        elif elegida == "4":
            return responder("menu", {}, CONSEJOS, MENU)
        elif elegida == "5":
            return responder("actualizar_direccion", {}, "Escribe tu nueva dirección. Usa «cancelar» para salir.")
        else:
            return responder("menu", {}, "No reconocí esa opción.", MENU)
    if estado == "actualizar_direccion":
        if not registro.texto_valido(texto, 5, 1000):
            return responder(estado, datos, "Escribe una dirección de entre 5 y 1000 caracteres.")
        return responder("actualizar_confirmacion", {"direccion": texto},
                         f"Nueva dirección: {texto}\n1. Confirmar · 2. Corregir · «cancelar».")
    if estado == "actualizar_confirmacion":
        if opcion in ("1", "confirmar", "si"):
            usuario.direccion = datos["direccion"]
            return responder("menu", {}, "Dirección actualizada.", MENU)
        if opcion in ("2", "corregir"):
            return responder("actualizar_direccion", {}, "Escribe la dirección corregida.")
        return responder(estado, datos, "Elige 1 para confirmar o 2 para corregir.")

    def ofrecer_materiales(borrador, motivo="Escribe los materiales que tienes o elige números separados por comas."):
        disponibles = catalogo(session)
        categoria = borrador.get("categoria")
        sugeridos = [m for m in disponibles if not categoria or m.categoria == categoria][:20]
        lista = "\n".join(f"{i}. {material.nombre}" for i, material in enumerate(sugeridos, 1))
        return responder("materiales", {**borrador, "opciones": [m.id for m in sugeridos]},
                         motivo + ("\n" + lista if lista else "\nNo hay opciones de ese tipo en el catálogo."))

    def seleccion(borrador):
        elegidos = set(borrador.get("materiales", []))
        return [m for m in catalogo(session) if m.id in elegidos]

    def resumen(borrador):
        elegidos = seleccion(borrador)
        if not elegidos or len(elegidos) != len(borrador.get("materiales", [])):
            return ofrecer_materiales(borrador, "El catálogo cambió. Selecciona de nuevo los materiales.")
        grupos = agrupados(elegidos)
        colectivos = dict(session.execute(select(Colectivo.tipo_flujo, Colectivo.nombre)
                          .where(Colectivo.activo, Colectivo.tipo_flujo.in_(grupos))).all())
        if grupos.keys() - colectivos.keys():
            return ofrecer_materiales(borrador, "Un colectivo no está disponible. Elige otros materiales o cancela.")
        resumen_materiales = "\n".join(f"{CATEGORIAS[flujo]} · {colectivos[flujo]}: {', '.join(m.nombre for m in items)}"
                                        for flujo, items in grupos.items())
        mensaje = (f"Resumen de tu solicitud\n{resumen_materiales}\nDirección: {borrador['direccion']}\n"
                   f"Horario preferido (sin confirmar): {borrador['horario']}\n"
                   f"Observaciones: {borrador.get('observaciones') or 'Ninguna'}\n"
                   "1. Confirmar solicitud · 2. Modificar información · 3. Cancelar.")
        return responder("confirmacion", borrador, mensaje)

    if estado == "tipo" and not foto:
        tipos = {"1": "organico", "organico": "organico", "organicos": "organico",
                 "2": "reciclable", "reciclable": "reciclable", "reciclables": "reciclable",
                 "3": None, "no estoy seguro": None}
        return responder("metodo", {"categoria": tipos[opcion]}, METODO) if opcion in tipos else responder(estado, datos, TIPOS)
    if estado in CAPTURA_FOTO:
        materiales = catalogo(session)
        incompleto = False
        if foto:
            encontrados, incompleto = materiales_ia(analisis, materiales)
            if not encontrados:
                return ofrecer_materiales(datos, resumen_foto(analisis) + "\nPuedes elegir materiales del catálogo por texto.")
        elif estado == "metodo" and opcion in ("1", "foto", "enviar una fotografia"):
            return responder("espera_imagen", datos, "Envía una foto o escribe «texto» para continuar manualmente.")
        elif opcion in ("texto", "escribir", "escribir los materiales que tienes") or (estado == "metodo" and opcion == "2"):
            return ofrecer_materiales(datos)
        elif estado == "materiales" and re.fullmatch(r"\d{1,2}(?:\s*,\s*\d{1,2})*", texto):
            indices = {int(n) for n in texto.split(",")}
            opciones = datos.get("opciones", [])
            if min(indices) < 1 or max(indices) > len(opciones):
                return ofrecer_materiales(datos, "Selecciona números de la lista.")
            ids = {opciones[i - 1] for i in indices}
            encontrados = [m for m in materiales if m.id in ids]
            if len(encontrados) != len(ids):
                return ofrecer_materiales(datos, "El catálogo cambió. Elige de nuevo.")
        elif opcion:
            partes = re.split(r"[,;]|\s+y\s+", texto, flags=re.IGNORECASE)
            grupos = [coincidencias(parte, materiales) for parte in partes]
            if any(len(grupo) != 1 for grupo in grupos):
                return ofrecer_materiales(datos, "La descripción es ambigua o contiene materiales fuera del catálogo activo. Elige las opciones que correspondan.")
            ids = {grupo[0].id for grupo in grupos}
            encontrados = [m for m in materiales if m.id in ids]
        else:
            return ofrecer_materiales(datos)
        if len(encontrados) > 30:
            return ofrecer_materiales(datos, "Selecciona como máximo 30 materiales.")
        lista = "\n".join(f"• {m.nombre} — {CATEGORIAS[m.categoria]}" for m in encontrados)
        avisos = " Algunos objetos quedaron fuera del catálogo." if incompleto else ""
        if len(agrupados(encontrados)) > 1:
            avisos += " Al confirmar se crearán solicitudes separadas por colectivo."
        revision = f"Revisa estos materiales:\n{lista}\n{avisos}\n1. Sí, continuar · 2. Corregir materiales · 3. Cancelar."
        return responder("revision_material", {**datos, "materiales": [m.id for m in encontrados]},
                         f"{resumen_foto(analisis)}\n\n{revision}" if foto else revision)
    if estado == "revision_material":
        if opcion in ("2", "corregir", "corregir materiales"):
            return ofrecer_materiales(datos)
        if opcion in ("1", "si", "continuar", "si continuar"):
            if "horario" in datos and "direccion" in datos:
                return resumen(datos)
            return responder("direccion", datos, f"Dirección registrada: {usuario.direccion}\n"
                             "1. Usarla · 2. Indicar otra." if usuario.direccion else "Escribe la dirección de recogida.")
        return responder(estado, datos, "Elige 1 para continuar, 2 para corregir o 3 para cancelar.")
    if estado in ("direccion", "direccion_nueva"):
        if estado == "direccion" and opcion in ("2", "otra", "indicar otra") and usuario.direccion:
            return responder("direccion_nueva", datos, "Escribe la dirección de recogida.")
        direccion = usuario.direccion if estado == "direccion" and opcion in ("1", "usarla") else texto
        if not direccion or not registro.texto_valido(direccion, 5, 1000):
            return responder(estado, datos, "Indica una dirección válida o elige 1 para usar la registrada.")
        nuevo = {**datos, "direccion": direccion}
        return resumen(nuevo) if "horario" in datos else responder("horario", nuevo, "¿Qué horario prefieres? Es una preferencia, no una cita.")
    if estado == "horario":
        if not registro.texto_valido(texto, 2, 500):
            return responder(estado, datos, "Indica un horario preferido, por ejemplo «mañana».")
        nuevo = {**datos, "horario": texto}
        return resumen(nuevo) if "observaciones" in datos else responder("observaciones", nuevo,
            "¿Tienes observaciones? Escríbelas o responde «omitir».")
    if estado == "observaciones":
        if not texto or len(texto) > 1000:
            return responder(estado, datos, "Escribe hasta 1000 caracteres o responde «omitir».")
        return resumen({**datos, "observaciones": None if opcion in ("omitir", "ninguna", "no") else texto})
    if estado == "editar":
        if opcion == "1":
            return ofrecer_materiales({**datos, "categoria": None})
        if opcion == "2":
            return responder("direccion_nueva", datos, "Escribe la dirección corregida.")
        if opcion == "3":
            return responder("horario", datos, "Escribe el nuevo horario preferido.")
        if opcion == "4":
            return responder("observaciones", datos, "Escribe las observaciones o responde «omitir».")
        return responder(estado, datos, "1. Materiales · 2. Dirección · 3. Horario · 4. Observaciones.")
    if estado == "confirmacion":
        if opcion in ("2", "modificar", "modificar informacion"):
            return responder("editar", datos, "¿Qué deseas cambiar? 1. Materiales · 2. Dirección · 3. Horario · 4. Observaciones.")
        if opcion not in ("1", "si", "confirmar", "confirmar solicitud"):
            return resumen(datos)
        elegidos = seleccion(datos)
        if not elegidos or len(elegidos) != len(datos["materiales"]):
            return ofrecer_materiales(datos, "El catálogo cambió. Confirma de nuevo los materiales.")
        try:
            with session.begin_nested():
                solicitudes = [services.create_request(session, usuario, SolicitudConfirmada(
                    direccion=datos["direccion"], horario_preferido=datos["horario"],
                    descripcion=datos.get("observaciones"),
                    materiales=[MaterialConfirmado(material_id=m.id) for m in items],
                ), origin="whatsapp") for items in agrupados(elegidos).values()]
        except HTTPException:
            return ofrecer_materiales(datos, "No se guardó ninguna solicitud. Revisa los materiales o consulta con la administración.")
        return responder("menu", {}, "¡Recolección solicitada! ♻️\n" +
                         "\n".join(f"Código: {item.codigo} · Estado: Recibida" for item in solicitudes) +
                         "\nEl coordinador de cada colectivo revisará tu solicitud.", MENU)
    return responder("menu", {}, "Volvamos a empezar.", MENU)


def agrupados(materiales):
    grupos = {}
    for item in materiales:
        grupos.setdefault(item.categoria, []).append(item)
    return grupos
