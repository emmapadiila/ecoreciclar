"""Habilita a residentes activos al completar el registro por WhatsApp."""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE FUNCTION eco_habilitar_registro_whatsapp() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            NEW.piloto_habilitado := true;
            RETURN NEW;
        END;
        $$;

        CREATE TRIGGER usuario_habilitar_registro_whatsapp
        BEFORE UPDATE OF nombre ON usuarios FOR EACH ROW
        WHEN (OLD.nombre = 'Pendiente de registro' AND NEW.nombre <> OLD.nombre
              AND NEW.rol = 'residente' AND NEW.activo AND NEW.whatsapp_id IS NOT NULL
              AND btrim(NEW.direccion) <> '')
        EXECUTE FUNCTION eco_habilitar_registro_whatsapp();

        UPDATE usuarios SET piloto_habilitado = true
        WHERE rol = 'residente' AND activo AND NOT piloto_habilitado
          AND whatsapp_id IS NOT NULL AND nombre <> 'Pendiente de registro'
          AND btrim(direccion) <> '';
    """)


def downgrade():
    # Las habilitaciones ya concedidas se conservan.
    op.execute("""
        DROP TRIGGER usuario_habilitar_registro_whatsapp ON usuarios;
        DROP FUNCTION eco_habilitar_registro_whatsapp();
    """)
