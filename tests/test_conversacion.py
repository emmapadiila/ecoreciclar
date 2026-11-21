from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.conversacion import MENU, procesar_evento
from backend.models import Conversacion, Material, Usuario
from backend.services import register_verified_message
from backend.whatsapp import MensajeEntrante


@pytest.fixture
def charla(database):
    contador = 0

    def enviar(texto="", *, remitente="DEMO-WA-REC", imagen=None):
        nonlocal contador
        contador += 1
        mid = f"wamid.demo-conversacion-{contador}"
        tipo = "text" if imagen is None else "image"
        with Session(database) as session, session.begin():
            usuario, mensaje, _ = register_verified_message(session, remitente, mid, "texto")
            conversacion = session.get(Conversacion, mensaje.conversacion_id, with_for_update=True)
            respuestas = procesar_evento(session, usuario, conversacion, MensajeEntrante(
                remitente, mid, tipo, texto=texto, analisis_imagen=imagen,
            ))
            return conversacion.estado_actual, " ".join(respuestas)

    return enviar


def test_registro_nuevo_habilitado_automaticamente(database, charla):
    def nuevo(texto):
        return charla(texto, remitente="DEMO-NUEVO")

    estado, respuesta = nuevo("Hola")
    assert estado == "registro_nombre" and "Bienvenido" in respuesta
    assert nuevo("")[0] == "registro_nombre"
    assert nuevo("Ana Ejemplo")[0] == "registro_perfil"
    assert nuevo("perfil inválido")[0] == "registro_perfil"
    assert nuevo("negocio")[0] == "registro_direccion"
    assert nuevo("!")[0] == "registro_direccion"
    assert nuevo("Calle de prueba 12")[0] == "registro_confirmacion"
    with Session(database) as session:
        user = session.scalar(select(Usuario).where(Usuario.whatsapp_id == "DEMO-NUEVO"))
        assert user.direccion is None
    assert "Registro básico guardado" in nuevo("confirmar registro")[1]
    assert "Saldo acumulado" in nuevo("Consultar mis puntos")[1]
    assert nuevo("Solicitar recolección")[0] == "tipo"
    with Session(database) as session:
        user = session.scalar(select(Usuario).where(Usuario.whatsapp_id == "DEMO-NUEVO"))
        assert (user.nombre, user.tipo_generador, user.direccion, user.piloto_habilitado) == (
            "Ana Ejemplo", "negocio", "Calle de prueba 12", True,
        )


def test_reconocimiento_menu_inesperado_cancela_y_vuelve(charla):
    assert "Hola de nuevo, DEMO Residente Reciclaje" in charla("Hóla 👋")[1]
    assert MENU in charla("opción inventada")[1]
    assert charla("Quiero solicitar una recolección")[0] == "tipo"
    assert charla("No estoy seguro")[0] == "metodo"
    assert charla("1")[0] == "espera_imagen"
    assert "Borrador cancelado" in charla("cancelar")[1]
    assert charla("1")[0] == "tipo"
    assert charla("volver al menú")[0] == "menu"
    assert "limpios y secos" in charla("Consejos")[1]


def test_inactivo_y_direccion_actualizada(database, charla):
    assert charla("Actualizar mis datos")[0] == "actualizar_direccion"
    assert charla("Calle de prueba 20")[0] == "actualizar_confirmacion"
    assert charla("2")[0] == "actualizar_direccion"
    assert charla("Calle de prueba 21")[0] == "actualizar_confirmacion"
    assert "Dirección actualizada" in charla("1")[1]
    with Session(database) as session, session.begin():
        user = session.scalar(select(Usuario).where(Usuario.whatsapp_id == "DEMO-WA-REC"))
        assert user.direccion == "Calle de prueba 21"
        user.activo = False
    assert "no está activa" in charla("2")[1]


def test_borrador_persistente_y_caducidad(database, charla):
    assert charla("solicitar")[0] == "tipo"
    assert charla("orgánicos")[0] == "metodo"
    with Session(database) as session, session.begin():
        conversa = session.scalar(select(Conversacion).join(Usuario).where(Usuario.whatsapp_id == "DEMO-WA-REC"))
        assert conversa.datos_temporales["categoria"] == "organico"
        conversa.datos_temporales = {
            **conversa.datos_temporales, "_vence": (datetime.now(timezone.utc) - timedelta(hours=1)).timestamp(),
        }
    assert "borrador venció" in charla("2")[1]
    with Session(database) as session:
        assert session.scalar(select(Conversacion)).datos_temporales == {}


@pytest.mark.parametrize("texto", ["tengo vidrio", "tengo material rechazado", "tengo botellas plásticas y aceite"])
def test_fuera_del_catalogo_o_ambiguo(charla, texto):
    estado, mensaje = charla(texto)
    assert estado == "materiales"
    assert "fuera del catálogo" in mensaje and "DEMO Material rechazado" not in mensaje


def test_catalogo_multiple_y_confirmacion_ia(charla, database):
    with Session(database) as session, session.begin():
        session.add(Material(nombre="Cartón", categoria="reciclable", aceptado=True))
    estado, mensaje = charla("Tengo tres botellas plásticas y cartón")
    assert estado == "revision_material" and "Cartón" in mensaje and "Botellas PET" in mensaje
    assert charla("2")[0] == "materiales"
    assert charla("texto")[0] == "materiales"
    assert charla(imagen={"estado": "error"})[0] == "materiales"
    estado, mensaje = charla(imagen={"estado": "completado", "residuos": [
        {"material": "PET", "nombre": "Botella", "categoria": "reciclable", "requiere_revision": True},
        {"material": "Poliestireno", "categoria": "reciclable"},
    ]})
    assert estado == "revision_material" and "fuera del catálogo" in mensaje
    assert charla("2")[0] == "materiales"
    assert "Cartón" in charla("cartón")[1]
    assert charla("1")[0] == "direccion"
