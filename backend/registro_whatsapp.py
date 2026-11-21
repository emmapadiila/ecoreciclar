"""Registro básico de residentes identificados por el transporte verificado."""

PENDIENTE = "Pendiente de registro"
BIENVENIDA = (
    "¡Hola! Bienvenido a EcoConecta 360. ♻️ Te ayudamos a gestionar tus residuos "
    "aprovechables. Para comenzar, vamos a verificar si ya estás registrado."
)
SIN_AUTORIZACION = (
    "Tu registro está guardado, pero la administración debe habilitarte en el piloto "
    "antes de que puedas crear solicitudes o consultar datos privados."
)
PREGUNTAS = {
    "registro_nombre": "¿Cuál es tu nombre completo?",
    "registro_perfil": "¿Qué tipo de participante eres? 1. Hogar · 2. Negocio.",
    "registro_direccion": "Escribe la dirección habitual de recogida.",
}


def registrado(usuario):
    return usuario.nombre != PENDIENTE


def texto_valido(texto, minimo, maximo):
    return minimo <= len(texto) <= maximo and any(char.isalnum() for char in texto)


def avanzar(usuario, estado, datos, texto, opcion):
    """Devuelve estado, borrador y respuesta. El llamador controla la transacción."""
    if estado == "registro_nombre":
        if (opcion == PENDIENTE.casefold() or not texto_valido(texto, 3, 120)
                or len(texto.split()) < 2 or not any(c.isalpha() for c in texto)):
            return estado, datos, "Escribe tu nombre completo (hasta 120 caracteres)."
        return "registro_perfil", {"nombre": texto}, PREGUNTAS["registro_perfil"]
    if estado == "registro_perfil":
        perfil = {"1": "hogar", "hogar": "hogar", "2": "negocio", "negocio": "negocio"}.get(opcion)
        if not perfil:
            return estado, datos, PREGUNTAS[estado]
        return "registro_direccion", {**datos, "tipo_generador": perfil}, PREGUNTAS["registro_direccion"]
    if estado == "registro_direccion":
        if not texto_valido(texto, 5, 1000):
            return estado, datos, "Escribe una dirección válida (entre 5 y 1000 caracteres)."
        datos = {**datos, "direccion": texto}
        return "registro_confirmacion", datos, (
            f"Confirma tus datos: {datos['nombre']} · {datos['tipo_generador']}\n"
            f"Dirección: {texto}\n1. Confirmar registro · 2. Corregir · 3. Cancelar."
        )
    if opcion in ("2", "corregir"):
        return "registro_nombre", {}, PREGUNTAS["registro_nombre"]
    if opcion not in ("1", "si", "confirmar", "confirmar registro"):
        return estado, datos, "Elige 1 para confirmar, 2 para corregir o 3 para cancelar."
    usuario.nombre = datos["nombre"]
    usuario.tipo_generador = datos["tipo_generador"]
    usuario.direccion = datos["direccion"]
    return "menu", {}, "¡Registro básico guardado!"
