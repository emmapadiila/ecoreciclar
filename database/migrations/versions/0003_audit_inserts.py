"""Solo el trigger de solicitudes puede insertar transiciones de estado."""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE FUNCTION eco_historial_insert() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF pg_trigger_depth() < 2 THEN
        RAISE EXCEPTION 'Historial solo mediante transición de solicitud' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER historial_insertar BEFORE INSERT ON historial_estados
      FOR EACH ROW EXECUTE FUNCTION eco_historial_insert();
    """)


def downgrade():
    op.execute("DROP TRIGGER historial_insertar ON historial_estados")
    op.execute("DROP FUNCTION eco_historial_insert()")
