from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend import services
from backend.auth import auth_secret, current_user, issue_token, verify_password
from backend.db import database_url, get_session
from backend.models import HistorialEstado, Material, MovimientoPuntos, Recoleccion, Usuario


@asynccontextmanager
async def lifespan(app):
    database_url()  # Cargar configuración, fallar antes de servir con secreto débil.
    auth_secret()
    yield


app = FastAPI(title="EcoConecta 360 — API de referencia", lifespan=lifespan)
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


class ScheduleInput(Input):
    programada_en: datetime

    @field_validator("programada_en")
    @classmethod
    def timezone_required(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Fecha y hora con zona obligatorias")
        return value


class CloseInput(Input):
    peso_real_kg: Decimal = Field(gt=0, max_digits=10, decimal_places=2, allow_inf_nan=False)


class TransitionInput(Input):
    estado: Literal["en_revision", "cancelada"]
    observacion: str = Field(min_length=1, max_length=1000)


def request_output(item):
    return {"id": item.id, "codigo": item.codigo, "colectivo_id": item.colectivo_id, "estado": item.estado}


@app.get("/health")
def health(session: DB):
    session.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.post("/auth/token")
def login(data: Login, session: DB):
    user = session.scalar(select(Usuario).where(Usuario.correo == data.correo.lower()))
    valid = verify_password(data.password, user.password_hash if user else None)
    if not valid or not user or not user.activo or not user.piloto_habilitado:
        raise HTTPException(401, "Credenciales inválidas o piloto no autorizado")
    return {"access_token": issue_token(user.id), "token_type": "bearer"}


@app.get("/materiales")
def materials(session: DB, user: User):
    return [{"id": m.id, "nombre": m.nombre, "categoria": m.categoria} for m in
            session.scalars(select(Material).where(Material.aceptado, Material.activo))]


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
    return {**request_output(item), "direccion": item.direccion, "descripcion": item.descripcion,
            "horario_preferido": item.horario_preferido}


@app.get("/solicitudes/{request_id}/historial")
def history(request_id: int, session: DB, user: User):
    services.request_for_user(session, user, request_id)
    return [{"anterior": h.estado_anterior, "nuevo": h.estado_nuevo, "actor_id": h.usuario_actor_id,
             "fecha": h.fecha, "observacion": h.observacion} for h in session.scalars(
                 select(HistorialEstado).where(HistorialEstado.solicitud_id == request_id).order_by(HistorialEstado.id))]


@app.post("/solicitudes/{request_id}/asignacion", status_code=201)
def assign(request_id: int, data: AssignmentInput, session: DB, user: User):
    item = services.assign(session, user, request_id, data.recolector_id)
    return {"id": item.id, "recolector_id": item.recolector_id}


@app.post("/solicitudes/{request_id}/programacion")
def schedule(request_id: int, data: ScheduleInput, session: DB, user: User):
    item = services.schedule(session, user, request_id, data.programada_en)
    return {"id": item.id, "programada_en": item.programada_en}


@app.post("/solicitudes/{request_id}/cierre")
def close(request_id: int, data: CloseInput, session: DB, user: User):
    item, points = services.close_collection(session, user, request_id, data.peso_real_kg)
    return {"recoleccion_id": item.id, "peso_real_kg": str(item.peso_real_kg), "puntos": str(points)}


@app.post("/solicitudes/{request_id}/estado")
def transition(request_id: int, data: TransitionInput, session: DB, user: User):
    return request_output(services.transition(session, user, request_id, data.estado, data.observacion))


@app.get("/mi-cuenta/puntos")
def points(session: DB, user: User):
    value = session.scalar(select(func.coalesce(func.sum(MovimientoPuntos.puntos), 0)).where(MovimientoPuntos.usuario_id == user.id))
    return {"usuario_id": user.id, "puntos": str(value)}
