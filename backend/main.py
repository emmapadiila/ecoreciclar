import os
from contextlib import asynccontextmanager
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend import services
from backend.whatsapp import router as whatsapp_router
from backend.auth import auth_secret, current_user, hash_password, issue_token, verify_password
from backend.db import database_url, get_session
from backend.models import (
    Colectivo,
    CoordinadorColectivo,
    EventoSolicitud,
    HistorialEstado,
    Material,
    MovimientoPuntos,
    Recoleccion,
    Recolector,
    SolicitudMaterial,
    Usuario,
)


@asynccontextmanager
async def lifespan(app):
    database_url()  # Cargar configuración, fallar antes de servir con secreto débil.
    auth_secret()
    yield


app = FastAPI(title="EcoConecta 360 — API de referencia", lifespan=lifespan)
app.include_router(whatsapp_router)
cors_origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "").split(",") if origin.strip()]
if cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
DB = Annotated[Session, Depends(get_session)]
User = Annotated[Usuario, Depends(current_user)]


@app.exception_handler(IntegrityError)
async def integrity_error(request, exc):
    # No devolver SQL, parámetros, direcciones ni datos personales de la excepción.
    return JSONResponse(status_code=409, content={"detail": "La operación viola una regla de integridad"})


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Login(Input):
    correo: str = Field(min_length=3, max_length=150)
    password: str = Field(min_length=1, max_length=256)


class RegisterInput(Input):
    nombre: str = Field(min_length=2, max_length=120)
    correo: str = Field(min_length=3, max_length=150)
    password: str = Field(min_length=12, max_length=256)
    confirm_password: str = Field(min_length=12, max_length=256)
    telefono: str | None = Field(default=None, max_length=20)
    direccion: str | None = Field(default=None, max_length=1000)
    tipo_generador: Literal["hogar", "negocio"] = "hogar"

    @field_validator("correo")
    @classmethod
    def normalize_correo(cls, value: str):
        value = value.lower()
        if "@" not in value:
            raise ValueError("Correo electrónico inválido")
        return value

    @field_validator("password")
    @classmethod
    def strong_password(cls, value: str):
        if not any(character.islower() for character in value) or not any(character.isupper() for character in value):
            raise ValueError("La contraseña debe incluir mayúsculas y minúsculas")
        if not any(character.isdigit() for character in value):
            raise ValueError("La contraseña debe incluir al menos un número")
        return value


class CreateUserInput(RegisterInput):
    rol: Literal["residente", "coordinador", "administrador"]
    activo: bool = True
    piloto_habilitado: bool = False
    colectivo_id: int | None = Field(default=None, gt=0)


class UpdateUserInput(Input):
    nombre: str | None = Field(default=None, min_length=2, max_length=120)
    correo: str | None = Field(default=None, min_length=3, max_length=150)
    telefono: str | None = Field(default=None, max_length=20)
    direccion: str | None = Field(default=None, max_length=1000)
    tipo_generador: Literal["hogar", "negocio"] | None = None
    rol: Literal["residente", "coordinador", "administrador"] | None = None
    activo: bool | None = None
    piloto_habilitado: bool | None = None
    password: str | None = Field(default=None, min_length=12, max_length=256)
    colectivo_id: int | None = Field(default=None, gt=0)


class MaterialInput(Input):
    material_id: int = Field(gt=0)
    estimado_kg: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2, allow_inf_nan=False)
    confirmado: bool


class RequestInput(Input):
    direccion: str = Field(min_length=1, max_length=1000)
    descripcion: str | None = Field(default=None, max_length=2000)
    horario_preferido: str | None = Field(default=None, max_length=500)
    materiales: list[MaterialInput] = Field(min_length=1, max_length=30)


class AssignmentInput(Input):
    recolector_id: int = Field(gt=0)


class NotesInput(Input):
    observaciones: str = Field(default="", max_length=1000)


class ScheduleInput(NotesInput):
    programada_en: AwareDatetime


class ContactInput(NotesInput):
    respuesta: Literal["aceptacion", "rechazo", "sin_respuesta", "pendiente"]
    recolector_id: int | None = Field(default=None, gt=0)


class PickupInput(NotesInput):
    fecha_real: AwareDatetime
    resultado: Literal["realizada", "incidencia"]


class ReceiptInput(NotesInput):
    fecha_real: AwareDatetime
    material: str = Field(min_length=1, max_length=200)


class WeightInput(NotesInput):
    peso_real_kg: Decimal = Field(gt=0, max_digits=10, decimal_places=2, allow_inf_nan=False)
    material: str = Field(min_length=1, max_length=200)


class CloseInput(Input):
    peso_real_kg: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2, allow_inf_nan=False)
    regla_id: int | None = Field(default=None, gt=0)
    puntos_previstos: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)


class TransitionInput(Input):
    estado: Literal["en_revision", "cancelada"]
    observacion: str = Field(min_length=1, max_length=1000)
    confirmar_materiales: bool = False


def request_output(item):
    return {"id": item.id, "codigo": item.codigo, "colectivo_id": item.colectivo_id, "estado": item.estado}


@app.get("/health")
def health(session: DB):
    session.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/public/resultados-diarios")
def public_daily_results(session: DB, fecha: date | None = None):
    day = fecha or datetime.now(ZoneInfo("America/Bogota")).date()
    if day == date.max:
        raise HTTPException(422, "Fecha fuera del rango admitido")
    return services.daily_results(session, day)


@app.post("/auth/token")
def login(data: Login, session: DB):
    user = session.scalar(select(Usuario).where(Usuario.correo == data.correo.strip().lower()))
    valid = verify_password(data.password, user.password_hash if user else None)
    if not valid or not user or not user.activo:
        raise HTTPException(401, "Credenciales inválidas")
    return {"access_token": issue_token(user.id), "token_type": "bearer"}


@app.post("/auth/register", status_code=201)
def register(data: RegisterInput, session: DB):
    if data.password != data.confirm_password:
        raise HTTPException(422, "Las contraseñas no coinciden")
    if session.scalar(select(Usuario.id).where(Usuario.correo == data.correo)):
        raise HTTPException(409, "Ya existe una cuenta con ese correo")
    user = Usuario(
        nombre=data.nombre,
        correo=data.correo,
        telefono=data.telefono,
        direccion=data.direccion,
        tipo_generador=data.tipo_generador,
        rol="residente",
        activo=True,
        piloto_habilitado=False,
        password_hash=hash_password(data.password),
    )
    session.add(user)
    session.flush()
    return {"id": user.id, "nombre": user.nombre, "correo": user.correo, "rol": user.rol}


@app.get("/auth/me")
def authenticated_user(user: User, session: DB):
    colectivo_tipo = None
    if user.rol == "coordinador":
        colectivo_tipo = session.scalar(
            select(Colectivo.tipo_flujo)
            .join(CoordinadorColectivo, CoordinadorColectivo.colectivo_id == Colectivo.id)
            .where(
                CoordinadorColectivo.usuario_id == user.id,
                CoordinadorColectivo.activo,
                Colectivo.activo,
            )
            .limit(1)
        )
    return {
        "id": user.id,
        "nombre": user.nombre,
        "correo": user.correo,
        "telefono": user.telefono,
        "direccion": user.direccion,
        "rol": user.rol,
        "tipo_generador": user.tipo_generador,
        "activo": user.activo,
        "piloto_habilitado": user.piloto_habilitado,
        "colectivo_tipo": colectivo_tipo,
    }


def require_admin(user: Usuario):
    if user.rol != "administrador":
        raise HTTPException(403, "Se requiere administrador")


def user_output(user: Usuario, colectivo_id: int | None = None):
    return {
        "id": user.id,
        "nombre": user.nombre,
        "correo": user.correo,
        "telefono": user.telefono,
        "direccion": user.direccion,
        "rol": user.rol,
        "tipo_generador": user.tipo_generador,
        "activo": user.activo,
        "piloto_habilitado": user.piloto_habilitado,
        "colectivo_id": colectivo_id,
    }


@app.get("/usuarios")
def list_users(session: DB, user: User):
    require_admin(user)
    rows = session.execute(
        select(Usuario, CoordinadorColectivo.colectivo_id)
        .outerjoin(CoordinadorColectivo, CoordinadorColectivo.usuario_id == Usuario.id)
        .order_by(Usuario.id)
    )
    seen = set()
    output = []
    for item, colectivo_id in rows:
        if item.id not in seen:
            output.append(user_output(item, colectivo_id))
            seen.add(item.id)
    return output


@app.post("/usuarios", status_code=201)
def create_user(data: CreateUserInput, session: DB, user: User):
    require_admin(user)
    if data.password != data.confirm_password:
        raise HTTPException(422, "Las contraseñas no coinciden")
    if data.rol == "administrador":
        raise HTTPException(403, "La creación de administradores requiere autorización explícita adicional")
    if data.rol == "coordinador" and data.colectivo_id is None:
        raise HTTPException(422, "El coordinador debe pertenecer a un colectivo")
    if data.colectivo_id is not None:
        collective = session.get(Colectivo, data.colectivo_id)
        if not collective or not collective.activo:
            raise HTTPException(422, "Colectivo inválido")
    correo = data.correo.lower()
    if session.scalar(select(Usuario.id).where(Usuario.correo == correo)):
        raise HTTPException(409, "Ya existe una cuenta con ese correo")
    created = Usuario(
        nombre=data.nombre, correo=correo, telefono=data.telefono, direccion=data.direccion,
        tipo_generador=data.tipo_generador, rol=data.rol, activo=data.activo,
        piloto_habilitado=data.piloto_habilitado, password_hash=hash_password(data.password),
    )
    session.add(created)
    session.flush()
    if data.rol == "coordinador":
        session.add(CoordinadorColectivo(usuario_id=created.id, colectivo_id=data.colectivo_id))
        session.flush()
    return user_output(created, data.colectivo_id)


@app.patch("/usuarios/{user_id}")
def update_user(user_id: int, data: UpdateUserInput, session: DB, user: User):
    require_admin(user)
    target = session.get(Usuario, user_id)
    if not target:
        raise HTTPException(404, "Usuario no encontrado")
    if user_id == user.id and data.rol not in (None, "administrador"):
        raise HTTPException(403, "No puede cambiarse su propio rol administrativo")
    if data.rol == "administrador":
        raise HTTPException(403, "La asignación de administrador requiere autorización explícita adicional")
    if data.correo is not None:
        data.correo = data.correo.lower()
        duplicate = session.scalar(select(Usuario.id).where(Usuario.correo == data.correo, Usuario.id != user_id))
        if duplicate:
            raise HTTPException(409, "Ya existe una cuenta con ese correo")
    for field in ("nombre", "correo", "telefono", "direccion", "tipo_generador", "rol", "activo", "piloto_habilitado"):
        value = getattr(data, field)
        if value is not None:
            setattr(target, field, value)
    if data.password:
        target.password_hash = hash_password(data.password)
    membership = session.scalar(select(CoordinadorColectivo).where(
        CoordinadorColectivo.usuario_id == target.id,
    ))
    if data.rol == "coordinador" or (target.rol == "coordinador" and data.colectivo_id is not None):
        if data.colectivo_id is None:
            raise HTTPException(422, "El coordinador debe pertenecer a un colectivo")
        collective = session.get(Colectivo, data.colectivo_id)
        if not collective or not collective.activo:
            raise HTTPException(422, "Colectivo inválido")
        if membership:
            membership.colectivo_id = data.colectivo_id
            membership.activo = True
        else:
            session.add(CoordinadorColectivo(usuario_id=target.id, colectivo_id=data.colectivo_id))
    elif target.rol != "coordinador" and membership:
        membership.activo = False
    session.flush()
    colectivo_id = data.colectivo_id
    if colectivo_id is None and membership:
        colectivo_id = membership.colectivo_id
    return user_output(target, colectivo_id)


@app.get("/materiales")
def materials(session: DB, user: User):
    return [{"id": m.id, "nombre": m.nombre, "categoria": m.categoria} for m in
            session.scalars(select(Material).where(Material.aceptado, Material.activo))]


@app.get("/recolectores")
def collectors(session: DB, user: User):
    if user.rol != "coordinador":
        raise HTTPException(403, "Se requiere coordinador")
    collective_ids = select(CoordinadorColectivo.colectivo_id).join(Colectivo).where(
        CoordinadorColectivo.usuario_id == user.id,
        CoordinadorColectivo.activo,
        Colectivo.activo,
    )
    workers = session.scalars(select(Recolector).where(
        Recolector.colectivo_id.in_(collective_ids), Recolector.activo,
    ).order_by(Recolector.nombre, Recolector.id))
    return [{"id": worker.id, "nombre": worker.nombre, "telefono": worker.telefono,
             "colectivo_id": worker.colectivo_id} for worker in workers]


@app.get("/colectivos")
def collectives(session: DB, user: User):
    require_admin(user)
    return [{"id": item.id, "nombre": item.nombre, "tipo_flujo": item.tipo_flujo, "activo": item.activo}
            for item in session.scalars(select(Colectivo).order_by(Colectivo.nombre))]


@app.get("/coordinadores")
def coordinators(session: DB, user: User):
    require_admin(user)
    rows = session.execute(
        select(Usuario, Colectivo)
        .join(CoordinadorColectivo, CoordinadorColectivo.usuario_id == Usuario.id)
        .join(Colectivo, Colectivo.id == CoordinadorColectivo.colectivo_id)
        .where(Usuario.rol == "coordinador", CoordinadorColectivo.activo, Usuario.activo)
        .order_by(Usuario.nombre)
    )
    return [{"id": item.id, "nombre": item.nombre, "correo": item.correo,
             "colectivo_id": collective.id, "colectivo": collective.nombre,
             "tipo_flujo": collective.tipo_flujo}
            for item, collective in rows]


@app.post("/solicitudes", status_code=201)
def create(data: RequestInput, session: DB, user: User):
    return request_output(services.create_request(session, user, data))


@app.get("/solicitudes")
def list_requests(session: DB, user: User, offset: int = 0):
    if offset < 0:
        raise HTTPException(422, "Offset no negativo")
    return [request_output(s) for s in session.scalars(services.scoped_requests(user).order_by("id").offset(offset).limit(100))]


@app.get("/solicitudes/{request_id}")
def detail(request_id: int, session: DB, user: User):
    item = services.request_for_user(session, user, request_id)
    assignment, latest, step = services.operation(session, item)
    owner = session.get(Usuario, item.usuario_id)
    collective = session.get(Colectivo, item.colectivo_id)
    worker = session.get(Recolector, assignment.recolector_id) if assignment else None
    materials = session.execute(select(Material.nombre, SolicitudMaterial.estimado_kg)
                                .join(SolicitudMaterial, SolicitudMaterial.material_id == Material.id)
                                .where(SolicitudMaterial.solicitud_id == item.id))
    pesaje = None
    cierre = None
    if step == "pesada" and user.rol == "coordinador":
        rule = services.rule_for(session, item, services.current_time())
        weight = Decimal(latest.datos["peso_real_kg"])
        pesaje = {**latest.datos, "regla_id": rule.id if rule else None,
                  "puntos_por_kg": str(rule.puntos_por_kg) if rule else None,
                  "puntos": str(services.points_for(weight, rule)) if rule else None}
    if item.estado == "recolectada":
        row = session.execute(select(Recoleccion.peso_real_kg, Recoleccion.fecha_recoleccion, MovimientoPuntos.puntos)
                              .join(MovimientoPuntos, MovimientoPuntos.recoleccion_id == Recoleccion.id)
                              .where(Recoleccion.solicitud_id == item.id)).one()
        cierre = dict(row._mapping)
    return {**request_output(item), "direccion": item.direccion, "descripcion": item.descripcion,
            "horario_preferido": item.horario_preferido, "paso": step, "residente": owner.nombre,
            "colectivo": collective.nombre, "fecha_creacion": item.fecha_creacion,
            "materiales": [{"nombre": nombre, "estimado_kg": kg} for nombre, kg in materials],
            "asignacion": {"recolector_id": worker.id, "nombre": worker.nombre,
                           "telefono": worker.telefono if user.rol == "coordinador" else None,
                           "fecha": assignment.fecha_asignacion, "programada_en": assignment.programada_en,
                           "observaciones": assignment.observaciones if user.rol == "coordinador" else None}
            if worker else None, "pesaje": pesaje, "cierre": cierre}


@app.get("/solicitudes/{request_id}/historial")
def history(request_id: int, session: DB, user: User):
    services.request_for_user(session, user, request_id)
    states = [{"anterior": h.estado_anterior, "nuevo": h.estado_nuevo, "actor_id": h.usuario_actor_id,
               "actor": name, "fecha": h.fecha, "observacion": h.observacion if user.rol == "coordinador" else None}
              for h, name in session.execute(select(HistorialEstado, Usuario.nombre)
                  .join(Usuario, Usuario.id == HistorialEstado.usuario_actor_id)
                  .where(HistorialEstado.solicitud_id == request_id).order_by(HistorialEstado.id))]
    operations = [{"tipo": e.tipo, "actor": name if user.rol == "coordinador" else "Coordinación",
                   "fecha": e.fecha, "datos": e.datos if user.rol == "coordinador" else {}}
                  for e, name in session.execute(select(EventoSolicitud, Usuario.nombre)
                      .join(Usuario, Usuario.id == EventoSolicitud.actor_id)
                      .where(EventoSolicitud.solicitud_id == request_id).order_by(EventoSolicitud.id))
                  if user.rol == "coordinador" or e.tipo in ("asignacion", "programacion", "recogida", "recepcion", "pesaje")
                  or (e.tipo == "confirmacion" and e.datos["respuesta"] == "aceptacion")]
    return sorted(states + operations, key=lambda event: event["fecha"])


@app.post("/solicitudes/{request_id}/asignacion", status_code=201)
def assign(request_id: int, data: AssignmentInput, session: DB, user: User):
    item = services.assign(session, user, request_id, data.recolector_id)
    return {"id": item.id, "recolector_id": item.recolector_id}


@app.post("/solicitudes/{request_id}/programacion")
def schedule(request_id: int, data: ScheduleInput, session: DB, user: User):
    item = services.schedule(session, user, request_id, data.programada_en, data.observaciones)
    return {"id": item.id, "programada_en": item.programada_en}


@app.post("/solicitudes/{request_id}/confirmacion")
def contact(request_id: int, data: ContactInput, session: DB, user: User):
    services.record_operation(session, user, request_id, "confirmacion", data)
    return {"registrada": True}


@app.post("/solicitudes/{request_id}/recogida")
def pickup(request_id: int, data: PickupInput, session: DB, user: User):
    services.record_operation(session, user, request_id, "recogida" if data.resultado == "realizada" else "incidencia", data)
    return {"registrada": True}


@app.post("/solicitudes/{request_id}/recepcion")
def receipt(request_id: int, data: ReceiptInput, session: DB, user: User):
    services.record_operation(session, user, request_id, "recepcion", data)
    return {"registrada": True}


@app.post("/solicitudes/{request_id}/pesaje")
def weigh(request_id: int, data: WeightInput, session: DB, user: User):
    services.record_operation(session, user, request_id, "pesaje", data)
    return {"registrado": True}


@app.post("/solicitudes/{request_id}/cierre")
def close(request_id: int, data: CloseInput, session: DB, user: User):
    item, points = services.close_collection(session, user, request_id, data.peso_real_kg, data.regla_id,
                                              data.puntos_previstos)
    return {"recoleccion_id": item.id, "peso_real_kg": str(item.peso_real_kg), "puntos": str(points)}


@app.post("/solicitudes/{request_id}/estado")
def transition(request_id: int, data: TransitionInput, session: DB, user: User):
    return request_output(services.transition(session, user, request_id, data.estado, data.observacion,
                                               data.confirmar_materiales))


@app.get("/mi-cuenta/puntos")
def points(session: DB, user: User):
    value = session.scalar(select(func.coalesce(func.sum(MovimientoPuntos.puntos), 0)).where(MovimientoPuntos.usuario_id == user.id))
    return {"usuario_id": user.id, "puntos": str(value)}
