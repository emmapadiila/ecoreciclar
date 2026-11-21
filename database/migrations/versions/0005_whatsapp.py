"""Amplía la auditoría de WhatsApp conservando las filas y estados existentes."""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE notificaciones
          ADD COLUMN proximo_intento timestamptz,
          DROP CONSTRAINT ck_notificaciones_estado,
          ADD CONSTRAINT ck_notificaciones_estado CHECK (estado IN ('pendiente','enviada','fallida','incierta'));
        ALTER TABLE mensajes_whatsapp
          ADD COLUMN notificacion_id bigint REFERENCES notificaciones(id),
          ADD COLUMN error_envio varchar(80),
          ADD COLUMN fecha_meta timestamptz,
          DROP CONSTRAINT ck_mensajes_whatsapp_envio,
          ADD CONSTRAINT ck_mensajes_whatsapp_envio CHECK
            (estado_envio IN ('pendiente','enviado','entregado','fallido','incierto','leido'));
        CREATE INDEX ix_mensajes_whatsapp_notificacion_id ON mensajes_whatsapp(notificacion_id);
    """)


def downgrade():
    raise RuntimeError("Conserve la revisión 0005 para preservar la auditoría de envíos.")
