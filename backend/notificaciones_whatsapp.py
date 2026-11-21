"""Despacho de la outbox existente. Ejecutar periódicamente con python -m."""
import logging
import os
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from backend import whatsapp_meta as meta
from backend.db import engine
from backend.models import Conversacion, MensajeWhatsapp, Notificacion, Usuario

logger = logging.getLogger(__name__)
MAX_INTENTOS = 3


def _carga(nota, ultima_entrada):
    if ultima_entrada and ultima_entrada > datetime.now(timezone.utc) - timedelta(hours=24):
        return meta.texto(nota.mensaje)
    nombre = os.getenv(f"WHATSAPP_TEMPLATE_{nota.tipo.upper()}", "")
    idioma = os.getenv("WHATSAPP_TEMPLATE_LANGUAGE", "")
    if not nombre or not idioma:
        raise meta.ErrorMeta("requiere_plantilla")
    return {"type": "template", "template": {"name": nombre, "language": {"code": idioma}}}


def _referencia(nota_id, intento):
    return f"saliente-sin-entrega-{nota_id}-{intento}"


def _disponible():
    return or_(Notificacion.proximo_intento.is_(None), Notificacion.proximo_intento <= func.now())


def despachar(bind, nota_id):
    with Session(bind) as sesion, sesion.begin():
        nota = sesion.scalar(select(Notificacion).where(
            Notificacion.id == nota_id, Notificacion.canal == "whatsapp",
            Notificacion.estado == "pendiente", Notificacion.intentos < MAX_INTENTOS, _disponible(),
        ).with_for_update(skip_locked=True))
        if nota is None:
            return
        # Reserva durable. Tras una caída se reconcilia con el callback de Meta.
        nota.intentos += 1
        nota.estado = "incierta"
        nota.proximo_intento = None
        destino = sesion.get(Usuario, nota.usuario_id).whatsapp_id or ""
        sesion.execute(insert(Conversacion).values(usuario_id=nota.usuario_id)
                       .on_conflict_do_nothing(index_elements=[Conversacion.usuario_id]))
        conv_id = sesion.scalar(select(Conversacion.id).where(Conversacion.usuario_id == nota.usuario_id))
        ultima = sesion.scalar(select(func.max(MensajeWhatsapp.fecha_meta)).where(
            MensajeWhatsapp.conversacion_id == conv_id, MensajeWhatsapp.direccion == "entrante",
        ))
        referencia = _referencia(nota.id, nota.intentos)
        causa = None
        try:
            carga = _carga(nota, ultima)
        except meta.ErrorMeta as error:
            carga = None
            causa = str(error)
            nota.estado = "fallida"
            logger.warning("Notificación %d: %s", nota_id, error)
        audit = MensajeWhatsapp(notificacion_id=nota.id, error_envio=causa, conversacion_id=conv_id, meta_message_id=referencia,
                                direccion="saliente", tipo="plantilla" if carga and carga["type"] == "template" else "texto",
                                contenido=nota.mensaje, estado_envio="incierto" if carga else "fallido")
        sesion.add(audit)
        sesion.flush()
        audit_id = audit.id
    if carga is None:
        return
    fallo = None
    try:
        wamid = meta.enviar(destino, carga, referencia)
    except meta.ErrorMeta as error:
        fallo = error
        logger.warning("Notificación %d: %s", nota_id, error)
    with Session(bind) as sesion, sesion.begin():
        nota = sesion.get(Notificacion, nota_id, with_for_update=True)
        audit = sesion.get(MensajeWhatsapp, audit_id, with_for_update=True)
        if audit.meta_message_id != referencia:
            return  # El webhook recibió el resultado antes que el cliente HTTP.
        if fallo is None:
            audit.meta_message_id = wamid
            audit.estado_envio = "enviado"
            nota.estado = "enviada"
        else:
            audit.error_envio = str(fallo)
            if fallo.incierto:
                return
            audit.estado_envio = "fallido"
            nota.estado = "fallida"
            if fallo.reintentar and nota.intentos < MAX_INTENTOS:
                nota.estado = "pendiente"
                nota.proximo_intento = datetime.now(timezone.utc) + timedelta(seconds=30 * 2 ** (nota.intentos - 1))


def registrar_estado(sesion, recibo):
    estados = {"sent": "enviado", "delivered": "entregado", "read": "leido", "failed": "fallido"}
    estado = estados.get(recibo.get("status"))
    wamid = recibo.get("id")
    if not estado or not wamid:
        return
    ids = [wamid]
    referencia = recibo.get("biz_opaque_callback_data", "")
    if re.fullmatch(r"saliente-sin-entrega-[1-9][0-9]{0,18}-[1-3]", referencia):
        ids.append(referencia)
    consulta = select(MensajeWhatsapp).where(
        MensajeWhatsapp.direccion == "saliente", MensajeWhatsapp.meta_message_id.in_(ids))
    fila = sesion.scalar(consulta)
    if fila is None:
        return
    # Mismo orden de bloqueos que el despachador.
    nota = sesion.get(Notificacion, fila.notificacion_id, with_for_update=True) if fila.notificacion_id else None
    audit = sesion.scalar(consulta.with_for_update().execution_options(populate_existing=True))
    if audit is None:
        return
    prioridad = {"pendiente": 0, "incierto": 0, "enviado": 1, "fallido": 2, "entregado": 3, "leido": 4}
    if prioridad[estado] < prioridad[audit.estado_envio]:
        return
    audit.meta_message_id = wamid
    audit.estado_envio = estado
    audit.error_envio = "meta_failed" if estado == "fallido" else None
    if nota:
        nota.estado = "fallida" if estado == "fallido" else "enviada"


def procesar_pendientes(bind, limite=100):
    with Session(bind) as sesion:
        ids = sesion.scalars(select(Notificacion.id).where(
            Notificacion.canal == "whatsapp", Notificacion.estado == "pendiente",
            Notificacion.intentos < MAX_INTENTOS, _disponible(),
        ).order_by(Notificacion.id).limit(limite)).all()
    for nota_id in ids:
        despachar(bind, nota_id)
    return len(ids)


if __name__ == "__main__":
    procesar_pendientes(engine())
