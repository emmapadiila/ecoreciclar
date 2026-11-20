from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import case, distinct, func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from backend.models import (
    Asignacion, Colectivo, Conversacion, CoordinadorColectivo, EventoSolicitud,
    Material, MensajeWhatsapp, MovimientoPuntos, Notificacion, Recoleccion, Recolector,
    ReglaPuntos, Solicitud, SolicitudMaterial, Usuario,
)


def set_actor(session: Session, user_id: int, observation: str = ""):
    session.execute(text("SELECT set_config('app.actor_id', :actor, true), set_config('app.observacion', :note, true)"),
                    {"actor": str(user_id), "note": observation})


def daily_results(session: Session, day: date):
    zone = ZoneInfo("America/Bogota")
    start = datetime.combine(day, time.min, tzinfo=zone)
    end = start + timedelta(days=1)
    kg = Recoleccion.peso_real_kg
    row = session.execute(select(
        func.coalesce(func.sum(kg), 0),
        func.coalesce(func.sum(case((Colectivo.tipo_flujo == "reciclable", kg), else_=0)), 0),
        func.coalesce(func.sum(case((Colectivo.tipo_flujo == "organico", kg), else_=0)), 0),
        func.count(Recoleccion.id),
        func.count(distinct(case((Solicitud.tipo_generador == "hogar", Solicitud.usuario_id)))),
        func.count(distinct(case((Solicitud.tipo_generador == "negocio", Solicitud.usuario_id)))),
        func.max(Recoleccion.fecha_recoleccion),
    ).select_from(Recoleccion).join(Solicitud, Solicitud.id == Recoleccion.solicitud_id)
      .join(Colectivo, Colectivo.id == Solicitud.colectivo_id)
      .where(Solicitud.estado == "recolectada", Recoleccion.fecha_recoleccion >= start,
             Recoleccion.fecha_recoleccion < end)).one()
    return {"fecha": day.isoformat(), "total_kg": row[0], "reciclables_kg": row[1],
            "organicos_kg": row[2], "recolecciones_confirmadas": row[3],
            "hogares_participantes": row[4], "negocios_participantes": row[5],
            "ultima_actualizacion": row[6]}


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


def current_time():
    return datetime.now(timezone.utc)


def operation(session: Session, request: Solicitud):
    assignment = session.scalar(select(Asignacion).where(Asignacion.solicitud_id == request.id))
    latest = session.scalar(select(EventoSolicitud).where(EventoSolicitud.solicitud_id == request.id)
                            .order_by(EventoSolicitud.id.desc()).limit(1))
    if request.estado in ("recibida", "en_revision", "recolectada", "cancelada"):
        return assignment, latest, request.estado
    if latest and latest.tipo == "confirmacion":
        step = {"aceptacion": "confirmada", "rechazo": "rechazada"}.get(latest.datos["respuesta"], "pendiente")
        if step == "confirmada" and request.estado == "programada":
            step = "programada"
    else:
        step = {"programacion": "programada", "incidencia": "incidencia", "recogida": "recogida",
                "recepcion": "recibida_material", "pesaje": "pesada"}.get(latest.tipo if latest else "", "pendiente")
    return assignment, latest, step


def add_event(session: Session, request: Solicitud, user: Usuario, kind: str, **data):
    session.add(EventoSolicitud(solicitud_id=request.id, actor_id=user.id, tipo=kind, datos=data))
    session.flush()


def assign(session: Session, user: Usuario, request_id: int, collector_id: int):
    request = request_for_user(session, user, request_id, lock=True, coordinator=True)
    assignment, latest, step = operation(session, request)
    set_actor(session, user.id)
    previous = None
    if step in ("recibida", "en_revision"):
        assignment = Asignacion(solicitud_id=request.id, colectivo_id=request.colectivo_id,
                                coordinador_id=user.id, recolector_id=collector_id)
        session.add(assignment)
    elif (assignment and latest and latest.tipo == "confirmacion" and
          assignment.recolector_id != collector_id and
          latest.datos["respuesta"] in ("rechazo", "sin_respuesta") and step in ("pendiente", "rechazada")):
        previous = assignment.recolector_id
        assignment.recolector_id = collector_id
        assignment.coordinador_id = user.id
        assignment.fecha_asignacion = current_time()
        assignment.programada_en = None
        assignment.observaciones = None
    else:
        raise HTTPException(409, "La solicitud no admite asignar ese responsable")
    session.flush()
    request.estado = "asignada"
    session.flush()
    add_event(session, request, user, "asignacion", recolector_id=collector_id, anterior_id=previous)
    return assignment


def schedule(session: Session, user: Usuario, request_id: int, when: datetime, notes: str = ""):
    request = request_for_user(session, user, request_id, lock=True, coordinator=True)
    assignment, _, step = operation(session, request)
    if step not in ("confirmada", "incidencia"):
        raise HTTPException(409, "Primero registre la aceptación telefónica o una incidencia")
    if when.tzinfo is None or when.utcoffset() is None:
        raise HTTPException(422, "Incluya zona horaria, por ejemplo -05:00")
    if when <= current_time():
        raise HTTPException(422, "La programación debe ser futura")
    set_actor(session, user.id)
    assignment.coordinador_id = user.id
    assignment.programada_en = when
    assignment.observaciones = notes
    session.flush()
    request.estado = "programada"
    session.flush()
    add_event(session, request, user, "programacion", fecha_real=when.isoformat(), observaciones=notes,
              recolector_id=assignment.recolector_id)
    notice = insert(Notificacion).values(usuario_id=request.usuario_id, solicitud_id=request.id, tipo="programacion",
                                         mensaje=f"Solicitud {request.codigo} programada: {when.isoformat()}")
    session.execute(notice.on_conflict_do_update(
        index_elements=[Notificacion.solicitud_id, Notificacion.tipo],
        set_={"mensaje": notice.excluded.mensaje, "estado": "pendiente", "intentos": 0},
    ))
    return assignment


def record_operation(session: Session, user: Usuario, request_id: int, kind: str, data):
    request = request_for_user(session, user, request_id, lock=True, coordinator=True)
    assignment, latest, step = operation(session, request)
    expected = {"confirmacion": {"pendiente", "rechazada"}, "recogida": {"programada"},
                "incidencia": {"programada"}, "recepcion": {"recogida"}, "pesaje": {"recibida_material"}}
    if not assignment or step not in expected[kind]:
        raise HTTPException(409, "Complete el paso anterior de la solicitud")
    expected_worker = getattr(data, "recolector_id", None)
    if expected_worker is not None and expected_worker != assignment.recolector_id:
        raise HTTPException(409, "El responsable cambió. Vuelva a consultar la solicitud.")
    when = getattr(data, "fecha_real", None)
    if when:
        earliest = assignment.programada_en if kind in ("recogida", "incidencia") else datetime.fromisoformat(latest.datos["fecha_real"])
        if when > current_time() or when < earliest:
            raise HTTPException(422, "La fecha real debe estar entre el paso anterior y el momento actual")
    set_actor(session, user.id)
    add_event(session, request, user, kind, recolector_id=assignment.recolector_id,
              **data.model_dump(mode="json", exclude={"recolector_id"}))


def rule_for(session: Session, request: Solicitud, instant: datetime, *, lock=False):
    query = select(ReglaPuntos).where(
        ReglaPuntos.colectivo_id == request.colectivo_id, ReglaPuntos.aprobada,
        ReglaPuntos.fecha_inicio <= instant,
        (ReglaPuntos.fecha_fin.is_(None)) | (ReglaPuntos.fecha_fin > instant),
    )
    return session.scalar(query.with_for_update(read=True) if lock else query)


def points_for(weight: Decimal, rule: ReglaPuntos):
    return (weight * rule.puntos_por_kg).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def close_collection(session: Session, user: Usuario, request_id: int, weight: Decimal | None = None,
                     rule_id: int | None = None, expected_points: Decimal | None = None):
    request = request_for_user(session, user, request_id, lock=True, coordinator=True)
    assignment, latest, step = operation(session, request)
    if step != "pesada":
        raise HTTPException(409, "La solicitud requiere un pesaje registrado y debe estar abierta")
    recorded_weight = Decimal(latest.datos["peso_real_kg"])
    if weight is not None and weight != recorded_weight:
        raise HTTPException(409, "El peso enviado no coincide con el pesaje registrado")
    set_actor(session, user.id)
    collection = Recoleccion(solicitud_id=request.id, asignacion_id=assignment.id,
                             peso_real_kg=recorded_weight, registrado_por=user.id,
                             observaciones=latest.datos.get("observaciones"))
    session.add(collection)
    session.flush()
    session.refresh(collection)
    # Se usa el instante de cierre asignado por PostgreSQL, no un reloj del cliente.
    rule = rule_for(session, request, collection.fecha_recoleccion, lock=True)
    if rule is None:
        raise HTTPException(409, "No existe regla aprobada vigente; cierre revertido")
    if rule_id is not None and rule.id != rule_id:
        raise HTTPException(409, "La regla de EcoPuntos cambió. Vuelva a consultar el pesaje.")
    points = points_for(recorded_weight, rule)
    if expected_points is not None and points != expected_points:
        raise HTTPException(409, "La estimación de EcoPuntos cambió. Vuelva a consultar el pesaje.")
    session.add(MovimientoPuntos(usuario_id=request.usuario_id, recoleccion_id=collection.id,
                                regla_id=rule.id, puntos=points, concepto="Recolección confirmada"))
    session.add(Notificacion(usuario_id=request.usuario_id, solicitud_id=request.id,
                             tipo="cierre", mensaje=f"Solicitud {request.codigo} cerrada; EcoPuntos: {points}"))
    session.flush()
    session.refresh(request)
    return collection, points


def transition(session: Session, user: Usuario, request_id: int, state: str, reason: str, confirm_materials=False):
    request = request_for_user(session, user, request_id, lock=True, coordinator=True)
    set_actor(session, user.id, reason)
    if state == "en_revision" and confirm_materials:
        session.execute(update(SolicitudMaterial).where(SolicitudMaterial.solicitud_id == request.id)
                        .values(confirmado=True))
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
