-- DATOS FICTICIOS. No ejecutar en producción. Repetible sin duplicar ni aprobar reglas.
INSERT INTO usuarios(nombre,correo,whatsapp_id,rol,piloto_habilitado,direccion,sector) VALUES
 ('DEMO Residente Reciclaje','residente.reciclaje@example.invalid','DEMO-WA-REC','residente',true,'DEMO sin dirección real','DEMO'),
 ('DEMO Residente Huerta','residente.huerta@example.invalid','DEMO-WA-ORG','residente',true,'DEMO sin dirección real','DEMO'),
 ('DEMO Coordinador Reciclaje','coordinador.reciclaje@example.invalid',NULL,'coordinador',true,NULL,'DEMO'),
 ('DEMO Coordinador Huerta','coordinador.huerta@example.invalid',NULL,'coordinador',true,NULL,'DEMO'),
 ('DEMO Administrador','admin@example.invalid',NULL,'administrador',true,NULL,'DEMO')
ON CONFLICT (correo) DO NOTHING;

INSERT INTO colectivos(nombre,tipo_flujo) VALUES
 ('DEMO Recicladores','reciclable'), ('DEMO Huerta','organico') ON CONFLICT (tipo_flujo) DO NOTHING;
INSERT INTO coordinadores_colectivo(usuario_id,colectivo_id)
 SELECT u.id,c.id FROM usuarios u JOIN colectivos c ON
  (u.correo='coordinador.reciclaje@example.invalid' AND c.tipo_flujo='reciclable') OR
  (u.correo='coordinador.huerta@example.invalid' AND c.tipo_flujo='organico')
ON CONFLICT (usuario_id,colectivo_id) DO NOTHING;
INSERT INTO recolectores(colectivo_id,nombre)
 SELECT id,'DEMO Integrante '||tipo_flujo FROM colectivos ON CONFLICT (colectivo_id,nombre) DO NOTHING;
INSERT INTO materiales(nombre,categoria,aceptado) VALUES
 ('DEMO Botellas PET','reciclable',true),('DEMO Restos vegetales','organico',true),
 ('DEMO Material rechazado','reciclable',false),('DEMO Residuo desconocido','otro',false)
ON CONFLICT (nombre) DO NOTHING;
INSERT INTO reglas_puntos(colectivo_id,puntos_por_kg,fecha_inicio,fecha_fin,aprobada)
 SELECT id,CASE WHEN tipo_flujo='reciclable' THEN 10 ELSE 5 END,
 '2020-01-01T00:00:00Z'::timestamptz,'2100-01-01T00:00:00Z'::timestamptz,false
 FROM colectivos ON CONFLICT (colectivo_id,fecha_inicio) DO NOTHING;
INSERT INTO configuraciones(clave,valor,descripcion) VALUES
 ('demo','true','DATOS FICTICIOS; no equivale a autorización real del piloto'),
 ('retencion_mensajes_dias','30','Propuesta técnica pendiente de validación del responsable; no tarea de borrado automática')
ON CONFLICT (clave) DO NOTHING;

DO $$
DECLARE f record; uid bigint; cid bigint; coord bigint; mid bigint; rid bigint; sid bigint;
BEGIN
 FOR f IN SELECT * FROM (VALUES
   ('reciclable','residente.reciclaje@example.invalid','DEMO Botellas PET','DEMO-ECO-REC'),
   ('organico','residente.huerta@example.invalid','DEMO Restos vegetales','DEMO-ECO-ORG')
 ) AS flows(flujo,correo,material,codigo)
 LOOP
  IF EXISTS(SELECT 1 FROM solicitudes WHERE codigo=f.codigo) THEN CONTINUE; END IF;
  SELECT id INTO uid FROM usuarios WHERE correo=f.correo;
  SELECT id INTO cid FROM colectivos WHERE tipo_flujo=f.flujo;
  SELECT usuario_id INTO coord FROM coordinadores_colectivo WHERE colectivo_id=cid AND activo ORDER BY id LIMIT 1;
  SELECT id INTO mid FROM materiales WHERE nombre=f.material;
  SELECT id INTO rid FROM recolectores WHERE colectivo_id=cid AND nombre='DEMO Integrante '||f.flujo;
  PERFORM set_config('app.actor_id',uid::text,true);
  PERFORM set_config('app.observacion','Escenario ficticio reproducible',true);
  INSERT INTO solicitudes(codigo,usuario_id,colectivo_id,tipo_generador,direccion,origen)
    VALUES(f.codigo,uid,cid,'hogar','DEMO punto de entrega ficticio','whatsapp') RETURNING id INTO sid;
  INSERT INTO solicitud_materiales(solicitud_id,material_id,estimado_kg,confirmado) VALUES(sid,mid,5,true);
  PERFORM set_config('app.actor_id',coord::text,true);
  INSERT INTO asignaciones(solicitud_id,colectivo_id,coordinador_id,recolector_id)
    VALUES(sid,cid,coord,rid);
  UPDATE solicitudes SET estado='asignada' WHERE id=sid;
  UPDATE asignaciones SET programada_en=now() - interval '1 day' WHERE solicitud_id=sid;
  UPDATE solicitudes SET estado='programada' WHERE id=sid;
  INSERT INTO notificaciones(usuario_id,solicitud_id,tipo,mensaje)
    VALUES(uid,sid,'programacion','DEMO programación ficticia; no enviar');
 END LOOP;
END $$;
