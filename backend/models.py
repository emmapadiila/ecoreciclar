"""Modelo único compartido con la API. Alembic es dueño del esquema físico."""
from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Column, DateTime, ForeignKey,
    ForeignKeyConstraint, Identity, Index, Integer, MetaData, Numeric,
    String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention={
        "ix": "ix_%(table_name)s_%(column_0_name)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    })


def pk():
    return Column(BigInteger, Identity(), primary_key=True, comment="Identificador interno estable")


def timestamp(description="Fecha de creación en UTC"):
    return Column(DateTime(timezone=True), nullable=False, server_default=func.now(), comment=description)


def active():
    return Column(Boolean, nullable=False, server_default="true", comment="Habilitación administrativa")


class Usuario(Base):
    __tablename__ = "usuarios"
    id = pk()
    nombre = Column(String(120), nullable=False, comment="Nombre visible; dato personal")
    telefono = Column(String(20), comment="Contacto privado opcional")
    whatsapp_id = Column(String(64), unique=True, comment="Identidad verificada por integración; NULL para cuenta web")
    correo = Column(String(150), unique=True, comment="Correo normalizado para acceso web")
    password_hash = Column(Text, comment="Hash scrypt con sal; nunca contraseña en claro")
    rol = Column(String(30), nullable=False, server_default="residente", comment="Rol validado en servidor")
    tipo_generador = Column(String(20), nullable=False, server_default="hogar", comment="Hogar o negocio")
    direccion = Column(Text, comment="Dirección privada; no se devuelve en listados públicos")
    sector = Column(String(120), comment="Sector del piloto")
    piloto_habilitado = Column(Boolean, nullable=False, server_default="false", comment="Autorización explícita del piloto")
    activo = active()
    fecha_registro = timestamp()
    __table_args__ = (
        CheckConstraint("rol IN ('residente','coordinador','administrador','recolector')", name="rol"),
        CheckConstraint("tipo_generador IN ('hogar','negocio')", name="generador"),
        CheckConstraint("whatsapp_id IS NULL OR length(trim(whatsapp_id)) > 0", name="identidad"),
    )


class Colectivo(Base):
    __tablename__ = "colectivos"
    id = pk()
    nombre = Column(String(100), nullable=False, comment="Nombre del colectivo")
    tipo_flujo = Column(String(20), nullable=False, unique=True, comment="Destino exclusivo: organico o reciclable")
    activo = active()
    __table_args__ = (CheckConstraint("tipo_flujo IN ('organico','reciclable')", name="flujo"),)


class CoordinadorColectivo(Base):
    __tablename__ = "coordinadores_colectivo"
    id = pk()
    usuario_id = Column(ForeignKey("usuarios.id"), nullable=False, comment="Usuario con rol coordinador")
    colectivo_id = Column(ForeignKey("colectivos.id"), nullable=False, comment="Ámbito del permiso")
    activo = active()
    __table_args__ = (UniqueConstraint("usuario_id", "colectivo_id"),)


class Recolector(Base):
    __tablename__ = "recolectores"
    id = pk()
    usuario_id = Column(ForeignKey("usuarios.id"), comment="Cuenta web opcional")
    colectivo_id = Column(ForeignKey("colectivos.id"), nullable=False, comment="Colectivo de pertenencia")
    nombre = Column(String(120), nullable=False, comment="Nombre del integrante")
    telefono = Column(String(20), comment="Contacto privado autorizado")
    activo = active()
    fecha_registro = timestamp()
    __table_args__ = (UniqueConstraint("id", "colectivo_id"), UniqueConstraint("colectivo_id", "nombre"))


class Material(Base):
    __tablename__ = "materiales"
    id = pk()
    nombre = Column(String(100), nullable=False, unique=True, comment="Material del catálogo controlado")
    categoria = Column(String(20), nullable=False, comment="Clasificación controlada")
    aceptado = Column(Boolean, nullable=False, server_default="false", comment="Aceptación por el piloto; no inferida por IA")
    activo = active()
    __table_args__ = (CheckConstraint("categoria IN ('organico','reciclable','otro')", name="categoria"),)


class Solicitud(Base):
    __tablename__ = "solicitudes"
    id = pk()
    codigo = Column(String(40), nullable=False, unique=True, comment="Código público aleatorio ECO-uuid; no secuencial inseguro")
    usuario_id = Column(ForeignKey("usuarios.id"), nullable=False, comment="Solicitante autorizado")
    colectivo_id = Column(ForeignKey("colectivos.id"), nullable=False, comment="Flujo único durante todo el ciclo")
    tipo_generador = Column(String(20), nullable=False, comment="Tipo declarado al crear la solicitud")
    descripcion = Column(Text, comment="Descripción opcional")
    direccion = Column(Text, nullable=False, comment="Dirección privada de recolección")
    horario_preferido = Column(Text, comment="Preferencia; no equivale a programación confirmada")
    origen = Column(String(20), nullable=False, comment="Canal de creación")
    estado = Column(String(30), nullable=False, server_default="recibida", comment="Estado auditado por trigger")
    fecha_creacion = timestamp()
    __table_args__ = (
        UniqueConstraint("id", "colectivo_id"),
        CheckConstraint("origen IN ('web','whatsapp')", name="origen"),
        CheckConstraint("tipo_generador IN ('hogar','negocio')", name="generador"),
        CheckConstraint("length(trim(direccion)) > 0", name="direccion"),
        CheckConstraint("estado IN ('recibida','en_revision','asignada','programada','recolectada','cancelada')", name="estado"),
        Index("ix_solicitudes_colectivo_estado_fecha", "colectivo_id", "estado", "fecha_creacion"),
    )


class SolicitudMaterial(Base):
    __tablename__ = "solicitud_materiales"
    id = pk()
    solicitud_id = Column(ForeignKey("solicitudes.id"), nullable=False, comment="Solicitud que contiene el material")
    material_id = Column(ForeignKey("materiales.id"), nullable=False, comment="Material del catálogo")
    descripcion = Column(Text, comment="Detalle del residuo")
    estimado_kg = Column(Numeric(10, 2), comment="Peso orientativo; jamás se usa para puntos")
    sugerencia_ia = Column(JSONB, comment="Resultado orientativo opcional")
    confirmado = Column(Boolean, nullable=False, server_default="false", comment="Confirmación humana del material")
    __table_args__ = (UniqueConstraint("solicitud_id", "material_id"), CheckConstraint("estimado_kg > 0", name="estimado"))


class Asignacion(Base):
    __tablename__ = "asignaciones"
    id = pk()
    solicitud_id = Column(BigInteger, nullable=False, unique=True, comment="Asignación vigente única en MVP")
    colectivo_id = Column(BigInteger, nullable=False, comment="Clave de ámbito usada por FKs compuestas")
    coordinador_id = Column(ForeignKey("usuarios.id"), nullable=False, comment="Actor autenticado que asigna")
    recolector_id = Column(BigInteger, nullable=False, comment="Integrante activo del mismo colectivo")
    programada_en = Column(DateTime(timezone=True), comment="Instante con zona; fecha y hora inseparables")
    observaciones = Column(Text, comment="Instrucciones privadas")
    fecha_asignacion = timestamp()
    __table_args__ = (
        UniqueConstraint("id", "solicitud_id"),
        ForeignKeyConstraint(["solicitud_id", "colectivo_id"], ["solicitudes.id", "solicitudes.colectivo_id"]),
        ForeignKeyConstraint(["recolector_id", "colectivo_id"], ["recolectores.id", "recolectores.colectivo_id"]),
    )


class HistorialEstado(Base):
    __tablename__ = "historial_estados"
    id = pk()
    solicitud_id = Column(ForeignKey("solicitudes.id"), nullable=False, comment="Solicitud auditada")
    usuario_actor_id = Column(ForeignKey("usuarios.id"), nullable=False, comment="Actor de la transacción; obligatorio")
    estado_anterior = Column(String(30), comment="NULL únicamente en la creación")
    estado_nuevo = Column(String(30), nullable=False, comment="Estado confirmado")
    observacion = Column(Text, comment="Motivo de la transición")
    fecha = timestamp("Instante de auditoría")
    __table_args__ = (Index("ix_historial_solicitud_fecha", "solicitud_id", "fecha"),)


class EventoSolicitud(Base):
    __tablename__ = "eventos_solicitud"
    id = pk()
    solicitud_id = Column(ForeignKey("solicitudes.id"), nullable=False)
    actor_id = Column(ForeignKey("usuarios.id"), nullable=False)
    tipo = Column(String(30), nullable=False)
    datos = Column(JSONB, nullable=False)
    fecha = timestamp()
    __table_args__ = (Index("ix_eventos_solicitud_orden", "solicitud_id", "id"),)


class Recoleccion(Base):
    __tablename__ = "recolecciones"
    id = pk()
    solicitud_id = Column(ForeignKey("solicitudes.id"), nullable=False, unique=True, comment="Una única recolección por solicitud")
    asignacion_id = Column(BigInteger, nullable=False, comment="Asignación de esta misma solicitud")
    peso_real_kg = Column(Numeric(10, 2), nullable=False, comment="Peso real confirmado; positivo y finito")
    fecha_recoleccion = timestamp("Momento del cierre confirmado")
    registrado_por = Column(ForeignKey("usuarios.id"), nullable=False, comment="Coordinador que confirma el peso")
    observaciones = Column(Text, comment="Resultado de la actividad")
    __table_args__ = (
        ForeignKeyConstraint(["asignacion_id", "solicitud_id"], ["asignaciones.id", "asignaciones.solicitud_id"]),
        CheckConstraint("peso_real_kg > 0 AND peso_real_kg < 'Infinity'::numeric", name="peso"),
    )


class ReglaPuntos(Base):
    __tablename__ = "reglas_puntos"
    id = pk()
    colectivo_id = Column(ForeignKey("colectivos.id"), nullable=False, comment="Colectivo al que aplica")
    puntos_por_kg = Column(Numeric(10, 2), nullable=False, comment="Factor configurable; no valor oficial")
    fecha_inicio = Column(DateTime(timezone=True), nullable=False, comment="Inicio inclusivo de vigencia")
    fecha_fin = Column(DateTime(timezone=True), comment="Fin exclusivo; NULL sin fin")
    aprobada = Column(Boolean, nullable=False, server_default="false", comment="Debe aprobarla un administrador autorizado")
    aprobada_por = Column(ForeignKey("usuarios.id"), comment="Administrador responsable de aprobación")
    __table_args__ = (
        UniqueConstraint("colectivo_id", "fecha_inicio"),
        CheckConstraint("puntos_por_kg >= 0 AND puntos_por_kg < 'Infinity'::numeric", name="factor"),
        CheckConstraint("fecha_fin IS NULL OR fecha_fin > fecha_inicio", name="vigencia"),
        CheckConstraint("NOT aprobada OR aprobada_por IS NOT NULL", name="aprobacion"),
    )


class MovimientoPuntos(Base):
    __tablename__ = "movimientos_puntos"
    id = pk()
    usuario_id = Column(ForeignKey("usuarios.id"), nullable=False, comment="Titular estable de los EcoPuntos")
    recoleccion_id = Column(ForeignKey("recolecciones.id"), nullable=False, unique=True, comment="Idempotencia de acreditación")
    regla_id = Column(ForeignKey("reglas_puntos.id"), nullable=False, comment="Versión inmutable de regla aplicada")
    puntos = Column(Numeric(12, 2), nullable=False, comment="Peso real por factor, redondeado a dos decimales")
    concepto = Column(String(100), nullable=False, comment="Motivo de acreditación")
    fecha = timestamp()
    __table_args__ = (CheckConstraint("puntos >= 0 AND puntos < 'Infinity'::numeric", name="puntos"),)


class Conversacion(Base):
    __tablename__ = "conversaciones"
    id = pk()
    usuario_id = Column(ForeignKey("usuarios.id"), nullable=False, unique=True, comment="Contexto único reutilizable; no es la identidad")
    estado_actual = Column(String(50), nullable=False, server_default="inicio", comment="Etapa del chatbot")
    datos_temporales = Column(JSONB, nullable=False, server_default="{}", comment="Contexto mínimo temporal; no secretos")
    fecha_inicio = timestamp()
    fecha_actualizacion = timestamp("Última actividad; actualizada por el servicio")


class MensajeWhatsapp(Base):
    __tablename__ = "mensajes_whatsapp"
    id = pk()
    conversacion_id = Column(ForeignKey("conversaciones.id"), nullable=False, comment="Conversación a la que pertenece")
    meta_message_id = Column(String(255), nullable=False, unique=True, comment="ID externo único; clave de idempotencia")
    direccion = Column(String(15), nullable=False, comment="Sentido del mensaje")
    tipo = Column(String(30), nullable=False, comment="Texto, imagen o respuesta")
    contenido = Column(Text, comment="Contenido privado mínimo con retención limitada")
    estado_envio = Column(String(30), nullable=False, server_default="pendiente", comment="Estado de entrega")
    estado_procesamiento = Column(String(30), nullable=False, server_default="pendiente", comment="Reintentos del procesamiento; separado de entrega")
    fecha = timestamp()
    __table_args__ = (
        CheckConstraint("direccion IN ('entrante','saliente')", name="direccion"),
        CheckConstraint("estado_envio IN ('pendiente','enviado','entregado','fallido')", name="envio"),
        CheckConstraint("estado_procesamiento IN ('pendiente','procesado','fallido')", name="proceso"),
    )


class ClasificacionIA(Base):
    __tablename__ = "clasificaciones_ia"
    id = pk()
    usuario_id = Column(ForeignKey("usuarios.id"), nullable=False, comment="Dueño del análisis")
    solicitud_id = Column(ForeignKey("solicitudes.id"), comment="Asociación opcional unidireccional; evita ciclo")
    imagen_referencia = Column(Text, comment="Clave privada de objeto; no URL pública permanente")
    objeto_detectado = Column(String(150), nullable=False, comment="Objeto sugerido")
    categoria_sugerida = Column(String(30), nullable=False, comment="Clasificación orientativa")
    aprovechable = Column(Boolean, nullable=False, comment="Sugerencia del modelo, no autorización")
    requiere_revision = Column(Boolean, nullable=False, server_default="true", comment="Revisión humana pendiente")
    categoria_confirmada = Column(String(30), comment="Clasificación humana opcional")
    modelo_ia = Column(String(100), nullable=False, comment="Modelo y versión usados")
    fecha = timestamp()
    __table_args__ = (
        CheckConstraint("categoria_sugerida IN ('organico','reciclable','otro')", name="sugerida"),
        CheckConstraint("categoria_confirmada IN ('organico','reciclable','otro')", name="confirmada"),
    )


class Notificacion(Base):
    __tablename__ = "notificaciones"
    id = pk()
    usuario_id = Column(ForeignKey("usuarios.id"), nullable=False, comment="Destinatario")
    solicitud_id = Column(ForeignKey("solicitudes.id"), comment="Solicitud relacionada")
    canal = Column(String(20), nullable=False, server_default="whatsapp", comment="Canal de entrega")
    tipo = Column(String(50), nullable=False, comment="Evento: programación o cierre")
    mensaje = Column(Text, nullable=False, comment="Contenido mínimo; evitar direcciones en mensajes")
    estado = Column(String(30), nullable=False, server_default="pendiente", comment="Outbox; no implica entrega real")
    intentos = Column(Integer, nullable=False, server_default="0", comment="Cantidad de intentos de envío")
    fecha_creacion = timestamp()
    __table_args__ = (
        UniqueConstraint("solicitud_id", "tipo"),
        CheckConstraint("estado IN ('pendiente','enviada','fallida')", name="estado"),
        CheckConstraint("intentos >= 0", name="intentos"),
        Index("ix_notificaciones_estado_fecha", "estado", "fecha_creacion"),
    )


class ContenidoAmbiental(Base):
    __tablename__ = "contenidos_ambientales"
    id = pk()
    titulo = Column(String(200), nullable=False, comment="Título editorial")
    categoria = Column(String(50), nullable=False, comment="Categoría educativa")
    contenido = Column(Text, nullable=False, comment="Texto educativo; sanitizar al renderizar HTML")
    imagen_url = Column(Text, comment="Imagen de contenido público, no foto de residente")
    publicado = Column(Boolean, nullable=False, server_default="false", comment="Control de publicación")
    fecha = timestamp()


class Configuracion(Base):
    __tablename__ = "configuraciones"
    id = pk()
    clave = Column(String(100), nullable=False, unique=True, comment="Nombre único del parámetro")
    valor = Column(JSONB, nullable=False, comment="Configuración no secreta")
    descripcion = Column(Text, nullable=False, comment="Propósito del parámetro")
    actualizado_en = timestamp("Última actualización, mantenida por el servicio")


# PostgreSQL no crea índices del lado referenciante: cubrir todas las FKs.
for table in Base.metadata.tables.values():
    for column in table.columns:
        if column.foreign_keys and not column.primary_key and not column.unique:
            if not any(list(index.columns)[0] is column for index in table.indexes):
                Index(f"ix_{table.name}_{column.name}", column)
