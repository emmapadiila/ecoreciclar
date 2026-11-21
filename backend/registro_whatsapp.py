"""Registro básico de residentes identificados por el transporte verificado."""

PENDIENTE = "Pendiente de registro"
BIENVENIDA = (
    "🌎 *¡Bienvenido a EcoConecta 360!* ♻️\n\n"
    "Te ayudamos a separar tus residuos y solicitar una recolección. Empecemos con tu registro."
)
CUENTA_INACTIVA = "🔐 *Cuenta inactiva*\n\nTu cuenta no está activa. Comunícate con la administración de EcoConecta para recibir ayuda."
PREGUNTAS = {
    "registro_nombre": "👤 *Tu nombre*\n\n¿Cuál es tu nombre completo?",
    "registro_perfil": "👤 *Tipo de participante*\n\n1️⃣ 🏠 Hogar\n2️⃣ 🏪 Negocio",
    "registro_direccion": "📍 *Dirección habitual*\n\nEscribe la dirección donde recogeremos tus residuos.",
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
            return estado, datos, "👤 Escribe tu nombre completo (hasta 120 caracteres)."
        return "registro_perfil", {"nombre": texto}, PREGUNTAS["registro_perfil"]
    if estado == "registro_perfil":
        perfil = {"1": "hogar", "hogar": "hogar", "2": "negocio", "negocio": "negocio"}.get(opcion)
        if not perfil:
            return estado, datos, PREGUNTAS[estado]
        return "registro_direccion", {**datos, "tipo_generador": perfil}, PREGUNTAS["registro_direccion"]
    if estado == "registro_direccion":
        if not texto_valido(texto, 5, 1000):
            return estado, datos, "📍 Escribe una dirección válida (entre 5 y 1000 caracteres)."
        datos = {**datos, "direccion": texto}
        return "registro_confirmacion", datos, (
            f"📋 *Confirma tus datos*\n\n👤 {datos['nombre']} · {datos['tipo_generador']}\n"
            f"📍 *Dirección:* {texto}\n\n1️⃣ ✅ Confirmar registro\n2️⃣ ✏️ Corregir\n3️⃣ ❌ Cancelar"
        )
    if opcion in ("2", "corregir"):
        return "registro_nombre", {}, PREGUNTAS["registro_nombre"]
    if opcion not in ("1", "si", "confirmar", "confirmar registro"):
        return estado, datos, "💬 Responde *1* para confirmar, *2* para corregir o *3* para cancelar."
    usuario.nombre = datos["nombre"]
    usuario.tipo_generador = datos["tipo_generador"]
    usuario.direccion = datos["direccion"]
    return "menu", {}, (f"🎉 *¡Registro completado!*\n\n¡Gracias, {usuario.nombre}! 😊\n"
                         "✅ Tus datos están guardados. Ya puedes solicitar recolecciones y consultar tus EcoPuntos.")
