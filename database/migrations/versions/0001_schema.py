"""Esquema inicial congelado, independiente de cambios futuros en los modelos."""
from pathlib import Path
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute(Path(__file__).with_suffix(".sql").read_text(encoding="utf-8"))


def downgrade():
    for table in (
        "movimientos_puntos", "recolecciones", "asignaciones", "historial_estados",
        "clasificaciones_ia", "solicitud_materiales", "notificaciones", "mensajes_whatsapp",
        "conversaciones", "solicitudes", "reglas_puntos", "coordinadores_colectivo",
        "recolectores", "materiales", "colectivos", "usuarios", "contenidos_ambientales", "configuraciones",
    ):
        op.drop_table(table)
