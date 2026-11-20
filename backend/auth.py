import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.db import get_session
from backend.models import Usuario

bearer = HTTPBearer(auto_error=False)


def auth_secret():
    secret = os.getenv("AUTH_SECRET", "")
    if len(secret) < 32:
        raise RuntimeError("AUTH_SECRET debe tener al menos 32 caracteres aleatorios")
    return secret


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    value = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(value).decode()


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded:
        # Mismo coste que un hash real para usuarios sin contraseña o inexistentes.
        hash_password(password)
        return False
    try:
        method, salt, expected = encoded.split("$")
        if method != "scrypt":
            return False
        value = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=16384, r=8, p=1)
        return hmac.compare_digest(value, base64.b64decode(expected))
    except (ValueError, TypeError):
        return False


def issue_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({
        "sub": str(user_id), "iat": now, "exp": now + timedelta(minutes=int(os.getenv("TOKEN_MINUTES", "30"))),
        "iss": "ecoconecta", "aud": "ecoconecta-api",
    }, auth_secret(), algorithm="HS256")


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: Session = Depends(get_session),
) -> Usuario:
    try:
        if credentials is None:
            raise ValueError("Sin credencial")
        claims = jwt.decode(
            credentials.credentials, auth_secret(), algorithms=["HS256"],
            issuer="ecoconecta", audience="ecoconecta-api", options={"require": ["sub", "exp", "iat"]},
        )
        user = session.get(Usuario, int(claims["sub"]))
        if not user or not user.activo or not user.piloto_habilitado:
            raise ValueError("Cuenta deshabilitada")
        return user
    except (jwt.InvalidTokenError, ValueError, TypeError) as exc:
        raise HTTPException(401, "Credenciales inválidas o piloto no autorizado", headers={"WWW-Authenticate": "Bearer"}) from exc
