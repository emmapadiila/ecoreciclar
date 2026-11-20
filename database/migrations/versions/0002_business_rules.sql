-- Parte inmutable de la revisión 0002. No ejecutar como esquema alternativo.
CREATE FUNCTION eco_actor() RETURNS bigint LANGUAGE plpgsql AS $$
DECLARE actor bigint;
BEGIN
  actor := nullif(current_setting('app.actor_id', true), '')::bigint;
  IF actor IS NULL OR NOT EXISTS (
    SELECT 1 FROM usuarios WHERE id=actor AND activo AND piloto_habilitado
  ) THEN RAISE EXCEPTION 'Actor activo y autorizado requerido' USING ERRCODE='23514'; END IF;
  RETURN actor;
END $$;

CREATE FUNCTION eco_coordinador(cid bigint) RETURNS bigint LANGUAGE plpgsql AS $$
DECLARE actor bigint := eco_actor();
BEGIN
  PERFORM 1 FROM coordinadores_colectivo cc JOIN usuarios u ON u.id=cc.usuario_id
    JOIN colectivos c ON c.id=cc.colectivo_id
    WHERE cc.usuario_id=actor AND cc.colectivo_id=cid AND cc.activo
      AND u.rol='coordinador' AND c.activo FOR SHARE OF cc, u, c;
  IF NOT FOUND THEN RAISE EXCEPTION 'Coordinador fuera de su colectivo' USING ERRCODE='23514'; END IF;
  RETURN actor;
END $$;

CREATE FUNCTION eco_solicitud() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE actor bigint := eco_actor();
BEGIN
  IF TG_OP='INSERT' THEN
    IF NEW.estado <> 'recibida' OR actor <> NEW.usuario_id THEN
      RAISE EXCEPTION 'Crear como solicitante en estado recibida' USING ERRCODE='23514';
    END IF;
    PERFORM 1 FROM usuarios WHERE id=NEW.usuario_id AND activo AND piloto_habilitado FOR SHARE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Solicitante no autorizado' USING ERRCODE='23514'; END IF;
    PERFORM 1 FROM colectivos WHERE id=NEW.colectivo_id AND activo FOR SHARE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Colectivo inactivo' USING ERRCODE='23514'; END IF;
    RETURN NEW;
  END IF;
  PERFORM eco_coordinador(OLD.colectivo_id);
  IF ROW(NEW.codigo,NEW.usuario_id,NEW.colectivo_id,NEW.tipo_generador,NEW.origen,NEW.fecha_creacion)
      IS DISTINCT FROM ROW(OLD.codigo,OLD.usuario_id,OLD.colectivo_id,OLD.tipo_generador,OLD.origen,OLD.fecha_creacion)
      OR OLD.estado IN ('recolectada','cancelada') THEN
    RAISE EXCEPTION 'Identidad y solicitudes terminadas son inmutables' USING ERRCODE='23514';
  END IF;
  IF NEW.estado <> OLD.estado THEN
    IF NOT ((OLD.estado='recibida' AND NEW.estado IN ('en_revision','asignada','cancelada'))
      OR (OLD.estado='en_revision' AND NEW.estado IN ('asignada','cancelada'))
      OR (OLD.estado='asignada' AND NEW.estado IN ('programada','cancelada'))
      OR (OLD.estado='programada' AND NEW.estado IN ('recolectada','cancelada'))) THEN
      RAISE EXCEPTION 'Transición inválida' USING ERRCODE='23514';
    END IF;
    IF NEW.estado IN ('asignada','programada') THEN
      IF NOT EXISTS (SELECT 1 FROM solicitud_materiales WHERE solicitud_id=NEW.id)
        OR EXISTS (SELECT 1 FROM solicitud_materiales sm JOIN materiales m ON m.id=sm.material_id
          JOIN colectivos c ON c.id=NEW.colectivo_id
          WHERE sm.solicitud_id=NEW.id AND (NOT sm.confirmado OR NOT m.aceptado OR NOT m.activo OR m.categoria<>c.tipo_flujo)) THEN
        RAISE EXCEPTION 'Materiales requieren aceptación y confirmación del flujo' USING ERRCODE='23514';
      END IF;
      IF NOT EXISTS (SELECT 1 FROM asignaciones a JOIN recolectores r ON r.id=a.recolector_id
        WHERE a.solicitud_id=NEW.id AND r.activo AND a.colectivo_id=NEW.colectivo_id
          AND (NEW.estado<>'programada' OR a.programada_en IS NOT NULL)) THEN
        RAISE EXCEPTION 'Responsable activo y programación completa requeridos' USING ERRCODE='23514';
      END IF;
    END IF;
    IF NEW.estado='recolectada' AND NOT EXISTS (SELECT 1 FROM recolecciones WHERE solicitud_id=NEW.id) THEN
      RAISE EXCEPTION 'Falta peso confirmado' USING ERRCODE='23514';
    END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER solicitud_validar BEFORE INSERT OR UPDATE ON solicitudes FOR EACH ROW EXECUTE FUNCTION eco_solicitud();

CREATE FUNCTION eco_auditar() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP='INSERT' THEN
    INSERT INTO historial_estados(solicitud_id,usuario_actor_id,estado_nuevo,observacion)
      VALUES(NEW.id,eco_actor(),NEW.estado,nullif(current_setting('app.observacion',true),''));
  ELSIF NEW.estado<>OLD.estado THEN
    INSERT INTO historial_estados(solicitud_id,usuario_actor_id,estado_anterior,estado_nuevo,observacion)
      VALUES(NEW.id,eco_actor(),OLD.estado,NEW.estado,nullif(current_setting('app.observacion',true),''));
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER solicitud_auditar AFTER INSERT OR UPDATE ON solicitudes FOR EACH ROW EXECUTE FUNCTION eco_auditar();

CREATE FUNCTION eco_material() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE s solicitudes; m materiales; flujo text;
BEGIN
  IF TG_OP='UPDATE' AND ROW(NEW.solicitud_id,NEW.material_id) IS DISTINCT FROM ROW(OLD.solicitud_id,OLD.material_id) THEN
    RAISE EXCEPTION 'No cambiar referencias de material' USING ERRCODE='23514';
  END IF;
  SELECT * INTO s FROM solicitudes WHERE id=NEW.solicitud_id FOR UPDATE;
  IF s.estado NOT IN ('recibida','en_revision') THEN
    RAISE EXCEPTION 'Materiales bloqueados después de asignar' USING ERRCODE='23514';
  END IF;
  IF eco_actor()<>s.usuario_id THEN PERFORM eco_coordinador(s.colectivo_id); END IF;
  SELECT * INTO m FROM materiales WHERE id=NEW.material_id FOR SHARE;
  SELECT tipo_flujo INTO flujo FROM colectivos WHERE id=s.colectivo_id;
  IF m.categoria<>flujo THEN RAISE EXCEPTION 'No mezclar flujos ni enrutar otros' USING ERRCODE='23514'; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER material_validar BEFORE INSERT OR UPDATE ON solicitud_materiales FOR EACH ROW EXECUTE FUNCTION eco_material();

CREATE FUNCTION eco_asignacion() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE s solicitudes; actor bigint;
BEGIN
  SELECT * INTO s FROM solicitudes WHERE id=NEW.solicitud_id FOR UPDATE;
  actor := eco_coordinador(s.colectivo_id);
  IF NEW.coordinador_id<>actor OR s.estado NOT IN ('recibida','en_revision','asignada') THEN
    RAISE EXCEPTION 'Asignación no autorizada o fuera de estado' USING ERRCODE='23514';
  END IF;
  IF TG_OP='UPDATE' AND ROW(NEW.solicitud_id,NEW.colectivo_id,NEW.recolector_id,NEW.coordinador_id)
      IS DISTINCT FROM ROW(OLD.solicitud_id,OLD.colectivo_id,OLD.recolector_id,OLD.coordinador_id) THEN
    RAISE EXCEPTION 'Reasignación no disponible en MVP' USING ERRCODE='23514';
  END IF;
  PERFORM 1 FROM recolectores WHERE id=NEW.recolector_id AND colectivo_id=s.colectivo_id AND activo FOR SHARE;
  IF NOT FOUND THEN RAISE EXCEPTION 'Recolector ajeno o inactivo' USING ERRCODE='23514'; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER asignacion_validar BEFORE INSERT OR UPDATE ON asignaciones FOR EACH ROW EXECUTE FUNCTION eco_asignacion();

CREATE FUNCTION eco_recoleccion() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE s solicitudes;
BEGIN
  SELECT * INTO s FROM solicitudes WHERE id=NEW.solicitud_id FOR UPDATE;
  IF eco_coordinador(s.colectivo_id)<>NEW.registrado_por OR s.estado<>'programada' THEN
    RAISE EXCEPTION 'Cierre no autorizado o ya realizado' USING ERRCODE='23514';
  END IF;
  PERFORM 1 FROM asignaciones a JOIN recolectores r ON r.id=a.recolector_id
    WHERE a.id=NEW.asignacion_id AND a.solicitud_id=s.id AND a.programada_en IS NOT NULL
      AND r.activo FOR SHARE OF a, r;
  IF NOT FOUND THEN RAISE EXCEPTION 'Asignación no válida para cierre' USING ERRCODE='23514'; END IF;
  NEW.fecha_recoleccion := clock_timestamp();
  RETURN NEW;
END $$;
CREATE TRIGGER recoleccion_validar BEFORE INSERT ON recolecciones FOR EACH ROW EXECUTE FUNCTION eco_recoleccion();

CREATE FUNCTION eco_cerrar() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  UPDATE solicitudes SET estado='recolectada' WHERE id=NEW.solicitud_id;
  RETURN NEW;
END $$;
CREATE TRIGGER recoleccion_cerrar AFTER INSERT ON recolecciones FOR EACH ROW EXECUTE FUNCTION eco_cerrar();

CREATE FUNCTION eco_regla() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  -- Serializar modificaciones de vigencia dentro de cada colectivo.
  PERFORM 1 FROM colectivos WHERE id=NEW.colectivo_id FOR UPDATE;
  IF TG_OP='UPDATE' AND EXISTS(SELECT 1 FROM movimientos_puntos WHERE regla_id=OLD.id) THEN
    RAISE EXCEPTION 'Regla aplicada inmutable: cree una nueva versión' USING ERRCODE='23514';
  END IF;
  IF NEW.aprobada THEN
    IF NEW.aprobada_por<>eco_actor() OR NOT EXISTS (
      SELECT 1 FROM usuarios WHERE id=NEW.aprobada_por AND rol='administrador' AND activo AND piloto_habilitado
    ) THEN RAISE EXCEPTION 'Aprobación administrativa requerida' USING ERRCODE='23514'; END IF;
    IF EXISTS(SELECT 1 FROM reglas_puntos r WHERE r.colectivo_id=NEW.colectivo_id AND r.aprobada
      AND r.id<>NEW.id AND tstzrange(r.fecha_inicio,r.fecha_fin,'[)') && tstzrange(NEW.fecha_inicio,NEW.fecha_fin,'[)')) THEN
      RAISE EXCEPTION 'Reglas aprobadas con vigencias superpuestas' USING ERRCODE='23514';
    END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER regla_validar BEFORE INSERT OR UPDATE ON reglas_puntos FOR EACH ROW EXECUTE FUNCTION eco_regla();

CREATE FUNCTION eco_puntos() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r recolecciones; s solicitudes; regla reglas_puntos;
BEGIN
  SELECT * INTO r FROM recolecciones WHERE id=NEW.recoleccion_id;
  SELECT * INTO s FROM solicitudes WHERE id=r.solicitud_id;
  PERFORM eco_coordinador(s.colectivo_id);
  SELECT * INTO regla FROM reglas_puntos WHERE id=NEW.regla_id FOR SHARE;
  IF s.estado IS DISTINCT FROM 'recolectada' OR NEW.usuario_id IS DISTINCT FROM s.usuario_id
      OR regla.id IS NULL OR NOT regla.aprobada OR regla.colectivo_id<>s.colectivo_id
      OR r.fecha_recoleccion<regla.fecha_inicio
      OR (regla.fecha_fin IS NOT NULL AND r.fecha_recoleccion>=regla.fecha_fin)
      OR NEW.puntos<>round(r.peso_real_kg*regla.puntos_por_kg,2) THEN
    RAISE EXCEPTION 'Acreditación inválida: cierre, titular, regla, vigencia o importe' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER puntos_validar BEFORE INSERT ON movimientos_puntos FOR EACH ROW EXECUTE FUNCTION eco_puntos();

CREATE FUNCTION eco_cierre_completo() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS(SELECT 1 FROM movimientos_puntos WHERE recoleccion_id=NEW.id) THEN
    RAISE EXCEPTION 'Cierre y puntos deben confirmarse en la misma transacción' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
CREATE CONSTRAINT TRIGGER cierre_atomico AFTER INSERT ON recolecciones
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION eco_cierre_completo();

CREATE FUNCTION eco_inmutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'Registro auditable inmutable: %', TG_TABLE_NAME USING ERRCODE='23514';
END $$;
CREATE TRIGGER historial_inmutable BEFORE UPDATE OR DELETE ON historial_estados FOR EACH ROW EXECUTE FUNCTION eco_inmutable();
CREATE TRIGGER puntos_inmutable BEFORE UPDATE OR DELETE ON movimientos_puntos FOR EACH ROW EXECUTE FUNCTION eco_inmutable();
CREATE TRIGGER recoleccion_inmutable BEFORE UPDATE OR DELETE ON recolecciones FOR EACH ROW EXECUTE FUNCTION eco_inmutable();
CREATE TRIGGER solicitud_no_borrar BEFORE DELETE ON solicitudes FOR EACH ROW EXECUTE FUNCTION eco_inmutable();
CREATE TRIGGER material_no_borrar BEFORE DELETE ON solicitud_materiales FOR EACH ROW EXECUTE FUNCTION eco_inmutable();
CREATE TRIGGER asignacion_no_borrar BEFORE DELETE ON asignaciones FOR EACH ROW EXECUTE FUNCTION eco_inmutable();
