"""
Segurança: hash de passwords e tokens JWT.

- Passwords nunca são guardadas em texto simples; guardamos apenas o hash bcrypt.
- A autenticação usa tokens JWT assinados com a SECRET_KEY da configuração.
"""
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import jwt, JWTError

from app.core.config import settings


# --- Passwords ---

def hash_password(plain_password: str) -> str:
    """Gera o hash bcrypt de uma password em texto simples."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica se a password corresponde ao hash guardado."""
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


# --- Tokens JWT ---

def create_access_token(subject: str, company_id: int, role: str) -> str:
    """
    Cria um token JWT.

    O token carrega, além do 'sub' (id do utilizador), o company_id e o role.
    Assim, cada pedido traz consigo o tenant e as permissões, sem nova consulta
    à base de dados só para descobrir a que empresa pertence.
    """
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub": str(subject),
        "company_id": company_id,
        "role": role,
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """Descodifica e valida um token JWT. Devolve o payload ou None se inválido."""
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None
