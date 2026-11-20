"""Integridad transaccional y auditoría PostgreSQL."""
from pathlib import Path
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(Path(__file__).with_suffix(".sql").read_text(encoding="utf-8"))


def downgrade():
    for function in (
        "eco_inmutable", "eco_cierre_completo", "eco_puntos", "eco_regla", "eco_cerrar",
        "eco_recoleccion", "eco_asignacion", "eco_material", "eco_auditar", "eco_solicitud",
    ):
        op.execute(f"DROP FUNCTION {function}() CASCADE")
    op.execute("DROP FUNCTION eco_coordinador(bigint)")
    op.execute("DROP FUNCTION eco_actor()")
