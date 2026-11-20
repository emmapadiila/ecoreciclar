from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from backend.models import (
    Asignacion, Colectivo, Conversacion, CoordinadorColectivo, HistorialEstado,
    Material, MensajeWhatsapp, MovimientoPuntos, Notificacion, Recoleccion,
    ReglaPuntos, Solicitud, SolicitudMaterial, Usuario,
)


def set_actor(session: Session, user_id: int, observation: str = ""):
    session.execute(text("SELECT set_config('app.actor_id', :actor, true), set_config('app.observacion', :note, true)"),
                    {"actor": str(user_id), "note": observation})


def scoped_requests(user: Usuario):
    query = select(Solicitud)
    if user.rol == "coordinador":
        return query.where(Solicitud.colectivo_id.in_(
            select(CoordinadorColectivo.colectivo_id).join(Colectivo).where(
                CoordinadorColectivo.usuario_id == user.id, CoordinadorColectivo.activo, Colectivo.activo,
            )
        ))
    if user.rol == "residente":
        return query.where(Solicitud.usuario_id == user.id)
    # No otorgar acceso global a PII por el mero rol administrador.
    raise HTTPException(403, "Rol sin acceso operativo")


def request_for_user(session: Session, user: Usuario, request_id: int, *, lock=False, coordinator=False):
    if coordinator and user.rol != "coordinador":
        raise HTTPException(403, "Se requiere coordinador")
    query = scoped_requests(user).where(Solicitud.id == request_id)
    if lock:
        query = query.with_for_update()
    request = session.scalar(query)
    if request is None:
        raise HTTPException(404, "Solicitud no encontrada")
    return request


def create_request(session: Session, user: Usuario, data, *, origin="web"):
    if not user.activo or not user.piloto_habilitado:
        raise HTTPException(403, "Usuario fuera del piloto")
    ids = [item.material_id for item in data.materiales]
    if len(ids) != len(set(ids)):
        raise HTTPException(422, "No repetir materiales")
    materials = list(session.scalars(select(Material).where(Material.id.in_(ids)).with_for_update(read=True)))
    categories = {material.categoria for material in materials}
    if len(materials) != len(ids) or len(categories) != 1 or not all(m.aceptado and m.activo for m in materials):
        raise HTTPException(422, "Material no aceptado o flujos mezclados; requiere revisión humana")
    collective = session.scalar(select(Colectivo).where(Colectivo.tipo_flujo == next(iter(categories)), Colectivo.activo))
    if collective is None:
        raise HTTPException(422, "Sin colectivo habilitado para estos materiales")
    set_actor(session, user.id)
    request = Solicitud(codigo="ECO-" + uuid4().hex, usuario_id=user.id, colectivo_id=collective.id,
                        tipo_generador=user.tipo_generador, direccion=data.direccion,
                        descripcion=data.descripcion, horario_preferido=data.horario_preferido, origen=origin)
    session.add(request)
    session.flush()
    session.add_all(SolicitudMaterial(solicitud_id=request.id, **item.model_dump()) for item in data.materiales)
    session.flush()
    return request


def assign(session: Session, user: Usuario, request_id: int, collector_id: int):
    request = request_for_user(session, user, request_id, lock=True, coordinator=True)
    if request.estado not in ("recibida", "en_revision"):
        raise HTTPException(409, "La solicitud no admite asignación")
    set_actor(session, user.id)
    assignment = Asignacion(solicitud_id=request.id, colectivo_id=request.colectivo_id,
                            coordinador_id=user.id, recolector_id=collector_id)
    session.add(assignment)
    session.flush()
    request.estado = "asignada"
    session.flush()
    return assignment


def schedule(session: Session, user: Usuario, request_id: int, when: datetime):
    request = request_for_user(session, user, request_id, lock=True, coordinator=True)
    if request.estado != "asignada":
        raise HTTPException(409, "Primero debe asignarse un responsable")
    if when.tzinfo is None or when.utcoffset() is None:
        raise HTTPException(422, "Incluya zona horaria, por ejemplo -05:00")
    set_actor(session, user.id)
    assignment = session.scalar(select(Asignacion).where(Asignacion.solicitud_id == request.id))
    assignment.programada_en = when
    session.flush()
    request.estado = "programada"
    session.add(Notificacion(usuario_id=request.usuario_id, solicitud_id=request.id,
                             tipo="programacion", mensaje=f"Solicitud {request.codigo} programada: {when.isoformat()}"))
    session.flush()
    return assignment


def close_collection(session: Session, user: Usuario, request_id: int, weight: Decimal):
    request = request_for_user(session, user, request_id, lock=True, coordinator=True)
    if request.estado != "programada":
        raise HTTPException(409, "Solicitud no programada o ya cerrada")
    set_actor(session, user.id)
    assignment = session.scalar(select(Asignacion).where(Asignacion.solicitud_id == request.id))
    collection = Recoleccion(solicitud_id=request.id, asignacion_id=assignment.id,
                             peso_real_kg=weight, registrado_por=user.id)
    session.add(collection)
    session.flush()
    session.refresh(collection)
    # Se usa el instante de cierre asignado por PostgreSQL, no un reloj del cliente.
    rule = session.scalar(select(ReglaPuntos).where(
        ReglaPuntos.colectivo_id == request.colectivo_id, ReglaPuntos.aprobada,
        ReglaPuntos.fecha_inicio <= collection.fecha_recoleccion,
        (ReglaPuntos.fecha_fin.is_(None)) | (ReglaPuntos.fecha_fin > collection.fecha_recoleccion),
    ).with_for_update(read=True))
    if rule is None:
        raise HTTPException(409, "No existe regla aprobada vigente; cierre revertido")
    points = (weight * rule.puntos_por_kg).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    session.add(MovimientoPuntos(usuario_id=request.usuario_id, recoleccion_id=collection.id,
                                regla_id=rule.id, puntos=points, concepto="Recolección confirmada"))
    session.add(Notificacion(usuario_id=request.usuario_id, solicitud_id=request.id,
                             tipo="cierre", mensaje=f"Solicitud {request.codigo} cerrada; EcoPuntos: {points}"))
    session.flush()
    session.refresh(request)
    return collection, points


def transition(session: Session, user: Usuario, request_id: int, state: str, reason: str):
    request = request_for_user(session, user, request_id, lock=True, coordinator=True)
    set_actor(session, user.id, reason)
    request.estado = state
    session.flush()
    return request


def register_verified_message(session: Session, whatsapp_id: str, message_id: str, kind: str):
    """Solo invocar DESPUÉS de verificar firma Meta y remitente. No es endpoint público.

    El worker toma la fila con FOR UPDATE, procesa y marca procesado en la misma
    transacción. Un fallo deja pendiente para reintento; recibir no implica procesar.
    """
    if not whatsapp_id.strip() or not message_id.strip():
        raise ValueError("Identificadores obligatorios")
    session.execute(insert(Usuario).values(whatsapp_id=whatsapp_id, nombre="Pendiente de registro")
                    .on_conflict_do_nothing(index_elements=[Usuario.whatsapp_id]))
    user = session.scalar(select(Usuario).where(Usuario.whatsapp_id == whatsapp_id))
    session.execute(insert(Conversacion).values(usuario_id=user.id)
                    .on_conflict_do_nothing(index_elements=[Conversacion.usuario_id]))
    conversation = session.scalar(select(Conversacion).where(Conversacion.usuario_id == user.id))
    message_id_created = session.scalar(insert(MensajeWhatsapp).values(
        conversacion_id=conversation.id, meta_message_id=message_id, direccion="entrante", tipo=kind,
    ).on_conflict_do_nothing(index_elements=[MensajeWhatsapp.meta_message_id]).returning(MensajeWhatsapp.id))
    existing = session.scalar(select(MensajeWhatsapp).where(MensajeWhatsapp.meta_message_id == message_id))
    if existing.conversacion_id != conversation.id:
        raise ValueError("Message ID ya vinculado a otra identidad")
    conversation.fecha_actualizacion = datetime.now(timezone.utc)
    session.flush()
    return user, existing, message_id_created is not None
