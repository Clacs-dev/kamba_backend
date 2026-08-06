"""
Dependências reutilizáveis das rotas (FastAPI Depends).

Aqui vive o coração do controlo de acesso:
- get_current_user: valida o token e devolve o utilizador autenticado.
- require_roles: restringe uma rota a certos perfis.

O company_id vem sempre do token do utilizador autenticado — NUNCA de um
parâmetro que o cliente possa manipular. É isto que garante o isolamento
entre empresas: um utilizador só consegue tocar nos dados da sua própria
empresa porque o company_id é imposto a partir da sua identidade.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.user import User
from app.models.enums import UserRole

# tokenUrl aponta para a rota de login; usado pelo /docs para o botão Authorize.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/token")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Não autenticado ou token inválido.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_access_token(token)
    if payload is None:
        raise credentials_error

    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_error

    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None or not user.is_active:
        raise credentials_error

    return user


def require_roles(*allowed_roles: UserRole):
    """
    Fábrica de dependências para restringir uma rota a certos perfis.

    Uso:
        @router.get("/algo")
        def rota(user: User = Depends(require_roles(UserRole.CAPITAL_HUMANO))):
            ...
    """
    def checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Não tem permissão para aceder a este recurso.",
            )
        return current_user

    return checker
