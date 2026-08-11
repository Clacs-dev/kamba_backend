"""
Rotas de gestão de colaboradores.

REGRA DE OURO (multi-tenant): todas as consultas filtram por
current_user.company_id — que vem do token, não de um parâmetro do cliente.
Um utilizador só vê e altera colaboradores da SUA empresa. Nunca se confia
num company_id enviado pelo cliente.

Permissões: criar, editar e desativar são reservados a Capital Humano e
Administração. Listar e ver são permitidos a esses mesmos perfis (os
colaboradores comuns têm o seu próprio portal, tratado noutro módulo).
"""
import secrets

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import hash_password
from app.models.user import User
from app.models.enums import UserRole
from app.schemas.collaborator import (
    CollaboratorCreate,
    CollaboratorUpdate,
    CollaboratorOut,
    CollaboratorCreatedOut,
)
from app.api.deps import require_roles

router = APIRouter(prefix="/collaborators", tags=["collaborators"])

# Perfis com poder de gestão de pessoas.
MANAGE_ROLES = (UserRole.CAPITAL_HUMANO, UserRole.ADMINISTRACAO)


def _get_company_user_or_404(db: Session, company_id: int, user_id: int) -> User:
    """
    Procura um utilizador pelo id MAS restrito à empresa indicada.
    Se não existir nessa empresa, devolve 404 — nunca revela que o id existe
    noutra empresa. Isto é parte do isolamento multi-tenant.
    """
    user = (
        db.query(User)
        .filter(User.id == user_id, User.company_id == company_id)
        .first()
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Colaborador não encontrado.",
        )
    return user


@router.post("", response_model=CollaboratorCreatedOut, status_code=status.HTTP_201_CREATED)
def create_collaborator(
    payload: CollaboratorCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    """
    Cria um colaborador na empresa do utilizador autenticado.
    Gera uma password temporária, devolvida uma única vez.
    """
    company_id = current_user.company_id

    # Email único dentro da empresa.
    exists = (
        db.query(User)
        .filter(User.company_id == company_id, User.email == payload.email)
        .first()
    )
    if exists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe um colaborador com este email nesta empresa.",
        )

    temp_password = secrets.token_urlsafe(9)  # ~12 caracteres legíveis

    collaborator = User(
        company_id=company_id,
        email=payload.email,
        hashed_password=hash_password(temp_password),
        full_name=payload.full_name,
        role=payload.role,
        must_change_password=True,  # obriga a trocar no primeiro acesso
    )
    db.add(collaborator)
    db.commit()
    db.refresh(collaborator)

    return CollaboratorCreatedOut(
        collaborator=CollaboratorOut.model_validate(collaborator),
        temporary_password=temp_password,
    )


@router.get("", response_model=list[CollaboratorOut])
def list_collaborators(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
    role: UserRole | None = Query(default=None, description="Filtrar por perfil"),
    is_active: bool | None = Query(default=None, description="Filtrar por estado"),
    search: str | None = Query(default=None, description="Procurar por nome ou email"),
):
    """Lista os colaboradores da empresa do utilizador, com filtros opcionais."""
    query = db.query(User).filter(User.company_id == current_user.company_id)

    if role is not None:
        query = query.filter(User.role == role)
    if is_active is not None:
        query = query.filter(User.is_active == is_active)
    if search:
        like = f"%{search}%"
        query = query.filter(
            (User.full_name.ilike(like)) | (User.email.ilike(like))
        )

    return query.order_by(User.full_name).all()


@router.get("/{collaborator_id}", response_model=CollaboratorOut)
def get_collaborator(
    collaborator_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    """Devolve um colaborador específico da empresa do utilizador."""
    return _get_company_user_or_404(db, current_user.company_id, collaborator_id)


@router.patch("/{collaborator_id}", response_model=CollaboratorOut)
def update_collaborator(
    collaborator_id: int,
    payload: CollaboratorUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    """Atualiza os dados de um colaborador da empresa do utilizador."""
    collaborator = _get_company_user_or_404(
        db, current_user.company_id, collaborator_id
    )

    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(collaborator, field, value)

    db.commit()
    db.refresh(collaborator)
    return collaborator


@router.post("/{collaborator_id}/deactivate", response_model=CollaboratorOut)
def deactivate_collaborator(
    collaborator_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    """
    Desativa um colaborador (não apaga — num sistema com histórico legal,
    desativa-se, preservando o registo). Impede desativar a própria conta.
    """
    if collaborator_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não pode desativar a sua própria conta.",
        )
    collaborator = _get_company_user_or_404(
        db, current_user.company_id, collaborator_id
    )
    collaborator.is_active = False
    db.commit()
    db.refresh(collaborator)
    return collaborator


@router.post("/{collaborator_id}/reactivate", response_model=CollaboratorOut)
def reactivate_collaborator(
    collaborator_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    """Reativa um colaborador previamente desativado."""
    collaborator = _get_company_user_or_404(
        db, current_user.company_id, collaborator_id
    )
    collaborator.is_active = True
    db.commit()
    db.refresh(collaborator)
    return collaborator
