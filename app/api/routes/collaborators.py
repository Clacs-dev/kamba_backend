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
from app.api.deps import require_roles, get_current_user

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
        id=collaborator.id,
        full_name=collaborator.full_name,
        email=collaborator.email,
        role=collaborator.role.value if hasattr(collaborator.role, "value") else str(collaborator.role),
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


# ---------- Documentos anexados do colaborador (contrato secção 2) ----------

from fastapi import UploadFile, File, Form
from app.models.collaborator_document import CollaboratorDocument
from app.services.cloudinary_upload import upload_file as _cloud_upload

_DOC_TYPES = ("bi", "contrato_assinado", "certificado_habilitacoes", "outro")


def _doc_out(d: CollaboratorDocument) -> dict:
    return {
        "id": d.id,
        "filename": d.filename,
        "doc_type": d.doc_type,
        "file_url": d.file_url,
        "uploaded_at": d.uploaded_at.isoformat(),
    }
@router.get("/me/documents")
def my_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """O próprio colaborador vê os seus documentos (BI, contrato, certificados)."""
    rows = (
        db.query(CollaboratorDocument)
        .filter(
            CollaboratorDocument.company_id == current_user.company_id,
            CollaboratorDocument.collaborator_id == current_user.id,
        )
        .order_by(CollaboratorDocument.id.desc())
        .all()
    )
    return [_doc_out(d) for d in rows]


@router.post("/{collaborator_id}/documents", status_code=201)
async def upload_collaborator_document(
    collaborator_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CAPITAL_HUMANO, UserRole.ADMINISTRACAO)),
    file: UploadFile = File(...),
    doc_type: str = Form(...),
):
    """O Capital Humano anexa um documento (BI, contrato, certificado) a um colaborador."""
    if doc_type not in _DOC_TYPES:
        raise HTTPException(status_code=422, detail="Tipo de documento inválido.")
    conteudo = await file.read()
    url = _cloud_upload(conteudo, file.filename, folder="kamba/colaboradores")
    doc = CollaboratorDocument(
        company_id=current_user.company_id,
        collaborator_id=collaborator_id,
        filename=file.filename,
        doc_type=doc_type,
        file_url=url,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return _doc_out(doc)


@router.get("/{collaborator_id}/documents")
def list_collaborator_documents(
    collaborator_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CAPITAL_HUMANO, UserRole.ADMINISTRACAO)),
):
    """Lista os documentos anexados a um colaborador."""
    rows = (
        db.query(CollaboratorDocument)
        .filter(
            CollaboratorDocument.company_id == current_user.company_id,
            CollaboratorDocument.collaborator_id == collaborator_id,
        )
        .order_by(CollaboratorDocument.id.desc())
        .all()
    )
    return [_doc_out(d) for d in rows]


@router.delete("/{collaborator_id}/documents/{doc_id}")
def delete_collaborator_document(
    collaborator_id: int,
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CAPITAL_HUMANO, UserRole.ADMINISTRACAO)),
):
    """Remove um documento anexado."""
    d = (
        db.query(CollaboratorDocument)
        .filter(
            CollaboratorDocument.id == doc_id,
            CollaboratorDocument.company_id == current_user.company_id,
        )
        .first()
    )
    if not d:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    db.delete(d)
    db.commit()
    return {"detail": "Documento removido."}


# ---------- Alterar o perfil (role) de um colaborador ----------

from pydantic import BaseModel as _BaseModel


class RoleUpdate(_BaseModel):
    role: UserRole


@router.patch("/{collaborator_id}/role", response_model=CollaboratorOut)
def change_role(
    collaborator_id: int,
    payload: RoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    """
    Altera o perfil (role) de um colaborador. Reservado a Capital Humano e
    Administração. Não permite alterar o próprio perfil (evita despromoção
    acidental do próprio gestor).
    """
    if collaborator_id == current_user.id:
        raise HTTPException(
            status_code=400,
            detail="Não pode alterar o seu próprio perfil.",
        )
    collaborator = (
        db.query(User)
        .filter(User.id == collaborator_id, User.company_id == current_user.company_id)
        .first()
    )
    if collaborator is None:
        raise HTTPException(status_code=404, detail="Colaborador não encontrado.")

    collaborator.role = payload.role
    db.commit()
    db.refresh(collaborator)

    # Notifica o colaborador da mudança de perfil.
    try:
        from app.services.notifications import notify
        notify(
            db, company_id=current_user.company_id, user_id=collaborator.id,
            title="Perfil de acesso atualizado",
            message=f"O seu perfil foi alterado para {payload.role.value}.",
            category="conta", link="/",
        )
        db.commit()
    except Exception:
        pass

    return CollaboratorOut.model_validate(collaborator)
