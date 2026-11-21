import asyncio
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import sys
import time
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from psycopg import sql
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from backend import ia_residuos as ia, whatsapp
from backend.conversacion import procesar_evento, resumen_foto
from backend.main import app
from backend.models import Colectivo, Conversacion, Notificacion, Solicitud, Usuario
from scripts import provision_runtime

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=")


def respuesta(*categorias):
    return {"analisis_id": "demo-prueba", "estado": "completado", "residuos": [
        {"id": f"obj-{i}", "nombre": "Botella" if categoria == "aprovechable" else "Restos vegetales",
         "material": "Plástico de botella" if categoria == "aprovechable" else None,
         "categoria": categoria, "requiere_revision": False, "material_id": 987654}
        for i, categoria in enumerate(categorias)
    ]}


@pytest.fixture
def motor(monkeypatch):
    monkeypatch.setenv("ECO_IA_URL", "http://reconocedor.invalid/api/ia/analizar-residuos")
    monkeypatch.setenv("ECO_IA_TIMEOUT", "5")

    def asignar(handler):
        monkeypatch.setattr(ia, "AsyncClient", lambda **opciones: httpx.AsyncClient(
            transport=httpx.MockTransport(handler), **opciones))

    return asignar


def test_foto_valida_normaliza_varios_residuos_y_sin_ids_de_catalogo(motor):
    def responder(request):
        assert request.url.path == "/api/ia/analizar-residuos"
        assert request.headers["Accept"] == "application/json"
        cuerpo = request.content
        assert all(item in cuerpo for item in (b'name="imagen"', PNG, b"image/png", b"foto-1", b"muestra"))
        return httpx.Response(200, json=respuesta("aprovechable", "orgánico", "no_aprovechable", "dudoso", None))

    motor(responder)
    resultado = ia.analizar_imagen(PNG, "image/png", "muestra", "foto-1")
    assert resultado["estado"] == "completado"
    assert [r["categoria"] for r in resultado["residuos"]] == ["reciclable", "organico", "otro", None, None]
    assert [r["colectivo_sugerido"] for r in resultado["residuos"]] == ["recicladores", "huerta", None, None, None]
    assert resultado["residuos"][0]["material"] == "Botella plástica"
    assert all(r["requiere_revision"] and "material_id" not in r for r in resultado["residuos"])
    assert resultado["resumen"] == {"total_objetos_detectados": 5, "reciclables": 1, "organicos": 1,
                                    "no_aprovechables": 1, "requiere_revision": True}


def test_foto_sin_residuos(motor):
    motor(lambda _: httpx.Response(200, json=respuesta()))
    resultado = ia.analizar_imagen(PNG, "image/png")
    assert resultado["estado"] == "completado" and resultado["residuos"] == []
    assert resultado["advertencias"] and not resultado["resumen"]["requiere_revision"]


@pytest.mark.parametrize(("datos", "mime"), [(b"corrupta", "image/png"), (PNG, "image/heic"), (PNG, "image/jpeg")])
def test_rechaza_imagen_o_tipo_invalido_sin_contactar_motor(motor, datos, mime):
    motor(lambda _: pytest.fail("La entrada inválida llegó al motor"))
    assert ia.analizar_imagen(datos, mime)["estado"] == "error"


def test_rechaza_foto_demasiado_grande(motor, monkeypatch):
    monkeypatch.setattr(ia, "MAX_IMAGEN", len(PNG) - 1)
    motor(lambda _: pytest.fail("La imagen supera el límite"))
    assert ia.analizar_imagen(PNG, "image/png")["estado"] == "error"


@pytest.mark.parametrize(("codigo", "datos"), [(422, {}), (503, {}), (502, {}), (200, {"estado": "error"}),
                                               (200, {"estado": "completado", "residuos": "malformado"})])
def test_archivo_corrupto_o_motor_indisponible_y_respuesta_invalida(motor, codigo, datos):
    motor(lambda _: httpx.Response(codigo, json=datos))
    resultado = ia.analizar_imagen(PNG, "image/png")
    assert resultado["estado"] == "error" and not resultado["residuos"]
    assert resultado["advertencias"]


def test_limita_respuesta_y_no_sigue_redirecciones(motor):
    motor(lambda _: httpx.Response(200, content=b"x" * (ia.MAX_RESPUESTA + 1)))
    assert ia.analizar_imagen(PNG, "image/png")["estado"] == "error"
    llamadas = []

    def redirigir(request):
        llamadas.append(request.url)
        return httpx.Response(307, headers={"Location": "https://otro.invalid"})

    motor(redirigir)
    assert ia.analizar_imagen(PNG, "image/png")["estado"] == "error"
    assert len(llamadas) == 1


def test_plazo_total_con_motor_lento(motor, monkeypatch):
    async def responder(_):
        await asyncio.sleep(2)
        pytest.fail("El timeout no interrumpió la espera")

    motor(responder)
    monkeypatch.setenv("ECO_IA_TIMEOUT", "0.01")
    resultado = ia.analizar_imagen(PNG, "image/png")
    assert resultado["estado"] == "error" and "tardó demasiado" in resultado["advertencias"][0]


@pytest.fixture
def runtime_ia(database, monkeypatch, request):
    with database.connect() as conn:
        if not conn.scalar(text("SELECT rolsuper OR rolcreaterole FROM pg_roles WHERE rolname=current_user")):
            pytest.skip("La prueba de privilegios requiere un administrador del clúster de tests")
    nombre = "eco_ia_" + secrets.token_hex(6)
    clave = secrets.token_urlsafe(32)
    panel = getattr(request, "param", None) == "panel"
    prefijo = "DB_PANEL" if panel else "DB_APP"
    monkeypatch.setenv(prefijo + "_USER", nombre)
    monkeypatch.setenv(prefijo + "_PASSWORD", clave)
    monkeypatch.setenv("TEST_DATABASE_URL", database.url.render_as_string(hide_password=False))
    monkeypatch.setattr(sys, "argv", ["provision_runtime", "--test"] + (["--panel"] if panel else []))
    provision_runtime.main()
    limitado = create_engine(database.url.set(username=nombre, password=clave))
    try:
        yield limitado
    finally:
        from backend.db import panel_engine
        if panel:
            panel_engine().dispose()
            panel_engine.cache_clear()
        limitado.dispose()
        with database.begin() as conn:
            cursor = conn.connection.driver_connection
            cursor.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(nombre)))
            cursor.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(nombre)))


def test_runtime_solo_puede_actualizar_columnas_permitidas(runtime_ia):
    with runtime_ia.connect() as conn:
        permisos = conn.execute(text("""SELECT attname FROM pg_attribute
          WHERE attrelid='usuarios'::regclass AND attnum>0 AND NOT attisdropped
          AND has_column_privilege(current_user,'usuarios',attname,'UPDATE')""")).scalars().all()
        assert set(permisos) == {"id", "nombre", "tipo_generador", "direccion"}
    with pytest.raises(DBAPIError) as error:
        with runtime_ia.begin() as conn:
            conn.execute(text("UPDATE usuarios SET piloto_habilitado=true WHERE whatsapp_id='DEMO-WA-REC'"))
    assert error.value.orig.sqlstate == "42501"


def test_resumen_foto_detalla_detecciones_y_consejos_sin_repetir():
    item = {"nombre": "Cáscara de fruta", "material": "DEMO Restos vegetales", "categoria": "organico",
            "recomendacion": "Separa el residuo de su empaque."}
    result = resumen_foto({"estado": "completado", "residuos": [item, item, {"categoria": None}]})
    assert "Orgánico: Cáscara de fruta (Restos vegetales) ×2" in result
    assert result.count(item["recomendacion"]) == 1
    assert "no pude clasificar" in result and "DEMO" not in result


@pytest.mark.parametrize(("categorias", "status", "esperado"), [
    (("organico",), 200, "Orgánico: Restos vegetales"),
    (("aprovechable",), 200, "Aprovechable: Botella plástica"),
    (("organico", "aprovechable"), 200, "Orgánico: Restos vegetales|Aprovechable: Botella plástica"),
    ((), 200, "Envía otra foto"),
    ((), 503, "No pude analizar la foto"),
    (None, 200, "No pude analizar la foto"),
])
def test_primera_foto_firmada_y_duplicado(database, client, motor, monkeypatch, categorias, status, esperado):
    assert app.state.procesar_evento is procesar_evento
    assert app.state.analizar_imagen is ia.analizar_imagen
    monkeypatch.setenv("WHATSAPP_PROVIDER", "meta")
    monkeypatch.setenv("META_APP_SECRET", "mock-webhook-ia-local")
    monkeypatch.delenv("WHATSAPP_PHONE_NUMBER_ID", raising=False)
    descargas, consultas, envios = [], [], []

    def descargar(media_id):
        descargas.append(media_id)
        return PNG if categorias is not None else None

    def reconocer(request):
        consultas.append(request)
        return httpx.Response(status, json=respuesta(*categorias))

    monkeypatch.setattr(whatsapp, "descargar_imagen", descargar)
    monkeypatch.setattr(whatsapp.meta, "enviar", lambda *args: envios.append(args) or "wamid.salida-foto")
    motor(reconocer)
    mensaje = {"from": "DEMO-WA-PRIMERA-FOTO", "id": "wamid.primera-foto", "type": "image",
               "timestamp": str(int(time.time())), "image": {"id": "123"}}
    cuerpo = json.dumps({"entry": [{"changes": [{"field": "messages", "value": {"messages": [mensaje]}}]}]}).encode()
    firma = hmac.new(b"mock-webhook-ia-local", cuerpo, hashlib.sha256).hexdigest()
    for nuevos in (1, 0):
        r = client.post("/webhooks/whatsapp", content=cuerpo, headers={"X-Hub-Signature-256": "sha256=" + firma})
        assert r.status_code == 200 and r.json()["nuevos"] == nuevos
    assert descargas == ["123"] and len(consultas) == (categorias is not None)
    assert len(envios) == 1
    with Session(database) as session:
        usuario = session.scalar(select(Usuario).where(Usuario.whatsapp_id == mensaje["from"]))
        salida = session.scalar(select(Notificacion.mensaje).where(Notificacion.usuario_id == usuario.id))
        assert all(fragmento in salida for fragmento in esperado.split("|"))
        assert session.scalar(select(Conversacion.estado_actual).where(Conversacion.usuario_id == usuario.id)) == "inicio"
        assert not session.scalar(select(Solicitud.id).where(Solicitud.usuario_id == usuario.id))


def test_webhook_con_runtime_texto_foto_y_fallback(database, client, headers, runtime_ia, motor, monkeypatch):
    codigo_demo = "DEMO-WA-IA"
    monkeypatch.setenv("META_APP_SECRET", "mock-webhook-ia-local")
    monkeypatch.delenv("WHATSAPP_PHONE_NUMBER_ID", raising=False)
    monkeypatch.setattr(whatsapp, "engine", lambda: runtime_ia)
    foto = PNG
    monkeypatch.setattr(whatsapp, "descargar_imagen", lambda _: foto)
    monkeypatch.setattr(whatsapp.outbox, "despachar", lambda *_: None)
    numero = 0

    def enviar(texto=None):
        nonlocal numero
        numero += 1
        mensaje = {"from": codigo_demo, "id": f"wamid.demo-ia-{numero}"}
        if texto is None:
            mensaje.update(type="image", image={"id": "123", "mime_type": whatsapp.meta.mime_imagen(foto)})
        else:
            mensaje.update(type="text", text={"body": texto})
        cuerpo = json.dumps({"entry": [{"changes": [{"field": "messages", "value": {"messages": [mensaje]}}]}]}).encode()
        firma = hmac.new(b"mock-webhook-ia-local", cuerpo, hashlib.sha256).hexdigest()
        r = client.post("/webhooks/whatsapp", content=cuerpo, headers={"X-Hub-Signature-256": "sha256=" + firma})
        assert r.status_code == 200, r.text

    for t in ("Hola", "Persona de Prueba", "Negocio", "Dirección de prueba 1", "1"):
        enviar(t)
    with Session(database) as session, session.begin():
        usuario = session.scalar(select(Usuario).where(Usuario.whatsapp_id == codigo_demo))
        assert (usuario.nombre, usuario.tipo_generador, usuario.direccion, usuario.rol, usuario.piloto_habilitado) == (
            "Persona de Prueba", "negocio", "Dirección de prueba 1", "residente", True)
        uid = usuario.id
        assert not session.scalar(select(Solicitud).where(Solicitud.usuario_id == uid))
    for t in ("Actualizar mis datos", "Dirección de prueba 2", "1",
              "Tengo restos vegetales", "1", "1", "Mañana", "omitir", "1"):
        enviar(t)
    for t in ("1", "No estoy seguro", "1"):
        enviar(t)
    motor(lambda _: httpx.Response(503))
    enviar()
    with Session(database) as session:
        assert session.scalar(select(Conversacion.estado_actual).where(Conversacion.usuario_id == uid)) == "materiales"
        assert any("por texto" in n.mensaje for n in session.scalars(
            select(Notificacion).where(Notificacion.usuario_id == uid)))
    enviar("Tengo botellas plásticas")
    enviar("cancelar")
    for t in ("1", "reciclable", "1"):
        enviar(t)
    url_real = os.getenv("ECO_IA_TEST_URL")
    if url_real:
        foto = Path(os.environ["ECO_IA_TEST_PHOTO"]).read_bytes()
        monkeypatch.setenv("ECO_IA_URL", url_real)
        monkeypatch.setenv("ECO_IA_TIMEOUT", "15")
        monkeypatch.setattr(ia, "AsyncClient", httpx.AsyncClient)
    else:
        motor(lambda _: httpx.Response(200, json=respuesta("aprovechable")))
    enviar()
    with Session(database) as session:
        assert session.scalar(select(Conversacion.estado_actual).where(Conversacion.usuario_id == uid)) == "revision_material"
        assert len(session.scalars(select(Solicitud).where(Solicitud.usuario_id == uid)).all()) == 1
    for t in ("1", "1", "Tarde", "omitir", "1"):
        enviar(t)
    with Session(database) as session:
        items = session.execute(select(Solicitud, Colectivo.tipo_flujo)
                                .join(Colectivo, Colectivo.id == Solicitud.colectivo_id)
                                .where(Solicitud.usuario_id == uid)).all()
        assert len(items) == 2
        assert {flow for _, flow in items} == {"organico", "reciclable"}
        for item, flow in items:
            assert item.origen == "whatsapp" and item.direccion == "Dirección de prueba 2"
            suffix = "huerta" if flow == "organico" else "reciclaje"
            respuesta_panel = client.get("/solicitudes", headers=headers[f"coordinador.{suffix}@example.invalid"])
            assert any(fila["codigo"] == item.codigo for fila in respuesta_panel.json())
    with Session(runtime_ia) as session, session.begin():
        usuario = session.get(Usuario, uid)
        conversacion = session.scalar(select(Conversacion).where(Conversacion.usuario_id == uid))
        evento_ajeno = whatsapp.MensajeEntrante("DEMO-WA-REC", "wamid.ajeno", "text", texto="Actualizar mis datos")
        with pytest.raises(ValueError, match="identidad"):
            procesar_evento(session, usuario, conversacion, evento_ajeno)


@pytest.mark.parametrize("runtime_ia", ["panel"], indirect=True)
def test_admin_borra_cuenta_y_puede_reutilizar_correo(database, client, headers, runtime_ia):
    admin = headers["admin@example.invalid"]
    email = "residente.reciclaje@example.invalid"
    with database.connect() as conn:
        uid = conn.scalar(text("SELECT id FROM usuarios WHERE correo=:email"), {"email": email})
        collective = conn.scalar(text("SELECT id FROM colectivos WHERE tipo_flujo='reciclable'"))
    path = f"/usuarios/{uid}"
    assert client.delete(path, headers=headers[email]).status_code == 403
    assert client.delete(path, headers=admin).status_code == 204
    assert client.delete(path, headers=admin).status_code == 204
    assert client.patch(path, json={"activo": True}, headers=admin).status_code == 404
    assert client.get("/auth/me", headers=headers[email]).status_code == 401
    with Session(database) as session:
        old = session.get(Usuario, uid)
        assert not old.activo and old.correo is None and old.whatsapp_id is None
        assert old.direccion is None and old.password_hash is None
        assert session.scalar(select(Solicitud.id).where(Solicitud.usuario_id == uid))
    assert all(user["id"] != uid for user in client.get("/usuarios", headers=admin).json())
    payload = {"nombre": "Cuenta de reemplazo", "correo": email, "password": "NuevaPrueba2026!",
               "confirm_password": "NuevaPrueba2026!", "tipo_generador": "hogar", "rol": "residente"}
    created = client.post("/usuarios", json=payload, headers=admin)
    assert created.status_code == 201 and created.json()["id"] != uid
    assert client.post("/auth/token", json={"correo": email, "password": payload["password"]}).status_code == 200
    coordinator = client.post("/usuarios", headers=admin, json={**payload, "rol": "coordinador",
        "correo": "coordinador.nuevo@example.invalid", "colectivo_id": collective})
    assert coordinator.status_code == 201, coordinator.text


@pytest.mark.parametrize("runtime_ia", ["panel"], indirect=True)
def test_administrador_publica_tarifas_con_vigencias_sin_superponer(database, client, headers, runtime_ia):
    admin = headers["admin@example.invalid"]
    coordinator = headers["coordinador.huerta@example.invalid"]
    with database.connect() as conn:
        group = conn.scalar(text("SELECT id FROM colectivos WHERE tipo_flujo='organico'"))
    initial = {"colectivo_id": group, "puntos_por_kg": "0.50"}
    assert client.post("/reglas-puntos", headers=coordinator, json=initial).status_code == 403
    assert client.get("/reglas-puntos", headers=coordinator).status_code == 403
    current = client.post("/reglas-puntos", headers=admin, json=initial)
    assert current.status_code == 201, current.text
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    future = client.post("/reglas-puntos", headers=admin, json={
        **initial, "puntos_por_kg": "0.75", "fecha_inicio": tomorrow,
    })
    assert future.status_code == 201, future.text
    assert client.post("/reglas-puntos", headers=admin, json=initial).status_code == 409
    first, second = client.get("/reglas-puntos", headers=admin).json()
    assert first["puntos_por_kg"] == "0.50" and second["puntos_por_kg"] == "0.75"
    assert first["fecha_fin"] == second["fecha_inicio"] and second["fecha_fin"] is None


@pytest.mark.parametrize("runtime_ia", ["panel"], indirect=True)
def test_openwa_foto_confirmacion_y_panel(database, client, headers, runtime_ia, motor, monkeypatch):
    from backend import whatsapp_openwa

    numero = "573000000001"
    chat = numero + "@c.us"
    monkeypatch.setenv("WHATSAPP_PROVIDER", "openwa")
    monkeypatch.setenv("OPENWA_SESSION_ID", "sesion")
    monkeypatch.setenv("OPENWA_URL", "http://openwa:2785")
    monkeypatch.setenv("OPENWA_API_KEY", "prueba")
    monkeypatch.setenv("OPENWA_WEBHOOK_SECRET", "secreto")
    respuestas = []
    def enviar(url, *, headers, timeout, json):
        assert url == "http://openwa:2785/api/sessions/sesion/messages/send-text"
        assert json["chatId"] == chat and headers["X-API-Key"] == "prueba"
        respuestas.append(json["text"])
        return httpx.Response(201, request=httpx.Request("POST", url), json={"messageId": str(len(respuestas))})

    monkeypatch.setattr(whatsapp_openwa.httpx, "post", enviar)
    def reconocer(req):
        assert PNG in req.content and b'name="imagen"' in req.content
        return httpx.Response(200, json=respuesta("aprovechable"))

    motor(reconocer)
    contador = 0
    def mensaje(body="", *, mid=None, image=False, sesion="sesion", firma=True, **fields):
        nonlocal contador
        contador += 1
        data = dict(id=mid or str(contador), chatId=chat, **{"from": chat}, timestamp=1800000000,
                    type="image" if image else "text", body=body, fromMe=False, isGroup=False, kind="individual")
        data.update(fields)
        if image:
            data["media"] = {"mimetype": "image/png", "data": base64.b64encode(PNG).decode()}
        raw = json.dumps({"sessionId": sesion, "event": "message.received", "data": data}).encode()
        dig = hmac.new(b"secreto", raw, hashlib.sha256).hexdigest()
        r = client.post("/webhooks/openwa", content=raw, headers={"X-OpenWA-Signature": "sha256=" + dig} if firma else {})
        assert r.status_code == (200 if firma else 403)
        return r.json().get("nuevos")

    mensaje("Hola", firma=False)
    assert mensaje("Hola", sesion="ajena") == mensaje("Hola", fromMe=True) == mensaje("Hola", isGroup=True) == 0
    for t in ("Hola", "Residente Prueba", "Hogar", "Casa prueba 123", "1"):
        assert mensaje(t) == 1
    admin = headers["admin@example.invalid"]
    usuarios = client.get("/usuarios", headers=admin).json()
    residente = next(u for u in usuarios if u["whatsapp_id"] == numero)
    assert residente["piloto_habilitado"] is True
    uid = residente["id"]
    for t in ("1", "reciclable", "foto"):
        mensaje(t)
    mensaje(image=True)
    assert "Aprovechable: Botella plástica" in respuestas[-1]
    assert "Confirma los materiales para la recolección" in respuestas[-1]
    assert "Botellas PET — Reciclable" in respuestas[-1] and "DEMO " not in respuestas[-1]
    mensaje("corregir")
    mensaje("Tengo botellas plásticas")
    assert "Revisa estos materiales" in respuestas[-1]
    for t in ("continuar", "1", "Tarde", "omitir"):
        mensaje(t)
    with Session(database) as session:
        assert not session.scalar(select(Solicitud).where(Solicitud.usuario_id == uid))
    assert mensaje("confirmar solicitud", mid="confirmacion") == 1
    total = len(respuestas)
    assert mensaje("confirmar solicitud", mid="confirmacion") == 0 and len(respuestas) == total
    mensaje("confirmar solicitud")
    with Session(database) as session:
        unica, = session.scalars(select(Solicitud).where(Solicitud.usuario_id == uid))
        assert unica.origen == "whatsapp" and any(unica.codigo in r for r in respuestas)
        filas = client.get("/solicitudes", headers=headers["coordinador.reciclaje@example.invalid"]).json()
        assert sum(f["codigo"] == unica.codigo for f in filas) == 1
