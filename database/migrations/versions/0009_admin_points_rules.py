"""Permite cerrar la vigencia de una tarifa sin cambiar puntos históricos."""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE OR REPLACE FUNCTION eco_regla() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE actor bigint; solo_fin boolean := false;
        BEGIN
          PERFORM 1 FROM colectivos WHERE id=NEW.colectivo_id FOR UPDATE;
          IF TG_OP='UPDATE' THEN
            solo_fin := OLD.aprobada AND NEW.fecha_fin IS NOT NULL
              AND (OLD.fecha_fin IS NULL OR NEW.fecha_fin < OLD.fecha_fin)
              AND (to_jsonb(NEW)-'fecha_fin') = (to_jsonb(OLD)-'fecha_fin');
            IF EXISTS (SELECT 1 FROM movimientos_puntos m JOIN recolecciones r ON r.id=m.recoleccion_id
                       WHERE m.regla_id=OLD.id AND (NOT solo_fin OR r.fecha_recoleccion>=NEW.fecha_fin)) THEN
              RAISE EXCEPTION 'La regla aplicada no puede alterar acreditaciones' USING ERRCODE='23514';
            END IF;
          END IF;
          IF NEW.aprobada THEN
            actor := eco_actor();
            IF (NOT solo_fin AND NEW.aprobada_por IS DISTINCT FROM actor) OR NOT EXISTS (
              SELECT 1 FROM usuarios WHERE id=actor AND rol='administrador' AND activo AND piloto_habilitado
            ) THEN RAISE EXCEPTION 'Aprobación administrativa requerida' USING ERRCODE='23514'; END IF;
            IF EXISTS (SELECT 1 FROM reglas_puntos r WHERE r.colectivo_id=NEW.colectivo_id AND r.aprobada
              AND r.id<>NEW.id AND tstzrange(r.fecha_inicio,r.fecha_fin,'[)') && tstzrange(NEW.fecha_inicio,NEW.fecha_fin,'[)')) THEN
              RAISE EXCEPTION 'Reglas aprobadas con vigencias superpuestas' USING ERRCODE='23514';
            END IF;
          END IF;
          RETURN NEW;
        END $$;
    """)


def downgrade():
    raise RuntimeError("Conserve la revisión 0009 para administrar las vigencias de EcoPuntos.")
