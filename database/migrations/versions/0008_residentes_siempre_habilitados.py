"""Todo residente con registro completo queda habilitado en el piloto, sin aprobación manual."""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        DROP TRIGGER IF EXISTS usuario_habilitar_registro_whatsapp ON usuarios;
        DROP FUNCTION IF EXISTS eco_habilitar_registro_whatsapp();

        CREATE OR REPLACE FUNCTION eco_habilitar_residente() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            NEW.piloto_habilitado := true;
            RETURN NEW;
        END;
        $$;

        -- Web, WhatsApp o panel: un residente registrado no puede quedar deshabilitado.
        -- Para bloquear una cuenta se usa "activo".
        DROP TRIGGER IF EXISTS usuario_residente_habilitado ON usuarios;
        CREATE TRIGGER usuario_residente_habilitado
        BEFORE INSERT OR UPDATE ON usuarios FOR EACH ROW
        WHEN (NEW.rol = 'residente' AND NEW.nombre <> 'Pendiente de registro'
              AND NOT NEW.piloto_habilitado)
        EXECUTE FUNCTION eco_habilitar_residente();

        UPDATE usuarios SET piloto_habilitado = true
        WHERE rol = 'residente' AND nombre <> 'Pendiente de registro' AND NOT piloto_habilitado;
    """)


def downgrade():
    # Las habilitaciones ya concedidas se conservan.
    op.execute("""
        DROP TRIGGER usuario_residente_habilitado ON usuarios;
        DROP FUNCTION eco_habilitar_residente();

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
    """)
