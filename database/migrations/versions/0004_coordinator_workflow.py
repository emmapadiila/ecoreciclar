"""Conserva los estados existentes y añade los hitos operativos auditados."""
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(Path(__file__).with_suffix(".sql").read_text(encoding="utf-8"))
    op.execute(request_trigger().replace(
        "('recolectada','cancelada')))",
        "('recolectada','cancelada','asignada')))",
    ).replace(
        "IF NEW.estado IN ('asignada','programada') THEN",
        """IF OLD.estado='programada' AND NEW.estado='asignada' AND NOT EXISTS (
          SELECT 1 FROM asignaciones WHERE solicitud_id=NEW.id AND programada_en IS NULL
        ) THEN RAISE EXCEPTION 'Reasignación requiere retirar programación' USING ERRCODE='23514'; END IF;
        IF NEW.estado IN ('asignada','programada') THEN""",
    ))


def request_trigger():
    previous = Path(__file__).with_name("0002_business_rules.sql").read_text(encoding="utf-8")
    function = previous.split("CREATE FUNCTION eco_solicitud()", 1)[1].split("CREATE TRIGGER solicitud_validar", 1)[0]
    return "CREATE OR REPLACE FUNCTION eco_solicitud()" + function


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM eventos_solicitud)")):
        raise RuntimeError("El historial operativo contiene datos. Conserve la revisión 0004.")
    op.execute("DROP TRIGGER recoleccion_pesaje_validar ON recolecciones")
    op.execute("DROP FUNCTION eco_recoleccion_pesaje()")
    op.execute("DROP TABLE eventos_solicitud")
    previous = Path(__file__).with_name("0002_business_rules.sql").read_text(encoding="utf-8")
    function = previous.split("CREATE FUNCTION eco_asignacion()", 1)[1].split("CREATE TRIGGER asignacion_validar", 1)[0]
    op.execute("CREATE OR REPLACE FUNCTION eco_asignacion()" + function)
    op.execute(request_trigger())
    op.execute("DROP FUNCTION eco_evento_solicitud()")
