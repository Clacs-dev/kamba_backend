"""
Rotas da ficha do colaborador (secção 2.1).

- O Capital Humano / Administração vê e atualiza a ficha de qualquer
  colaborador da sua empresa.
- O próprio colaborador consulta a sua ficha (mas não a edita — pode requerer
  correções por outra via, a implementar depois).

Isolamento multi-tenant: a ficha é sempre procurada dentro da empresa do
utilizador autenticado.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.models.enums import UserRole
from app.models.employee_profile import EmployeeProfile
from app.models.shift import Shift
from app.schemas.profile import ProfileUpdate, ProfileOut
from app.api.deps import get_current_user, require_roles

router = APIRouter(tags=["profiles"])

MANAGE_ROLES = (UserRole.CAPITAL_HUMANO, UserRole.ADMINISTRACAO, UserRole.ADMIN)


def _get_or_create_profile(db: Session, user: User) -> EmployeeProfile:
    """Devolve a ficha do utilizador, criando-a vazia se ainda não existir."""
    profile = (
        db.query(EmployeeProfile)
        .filter(EmployeeProfile.user_id == user.id)
        .first()
    )
    if profile is None:
        profile = EmployeeProfile(user_id=user.id, company_id=user.company_id)
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


def _profile_out(db: Session, profile: EmployeeProfile) -> ProfileOut:
    """Monta o ProfileOut acrescentando a tag calculada de assinaturas pendentes."""
    from app.models.dossier import Signature
    from app.models.enums import SignatureType
    assinadas = {
        s.signature_type for s in
        db.query(Signature).filter(Signature.user_id == profile.user_id).all()
    }
    obrigatorias = {
        SignatureType.REGULAMENTO_POLITICAS,
        SignatureType.TERMOS_PORTAL,
        SignatureType.CONSENTIMENTO_DADOS,
    }
    pendente = not obrigatorias.issubset(assinadas)
    out = ProfileOut.model_validate(profile)
    out.policies_signature_pending = pendente
    return out


@router.get("/me/profile", response_model=ProfileOut)
def get_my_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """O colaborador consulta a sua própria ficha."""
    return _profile_out(db, _get_or_create_profile(db, current_user))


@router.get("/collaborators/{collaborator_id}/profile", response_model=ProfileOut)
def get_collaborator_profile(
    collaborator_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    """O Capital Humano vê a ficha de um colaborador da sua empresa."""
    collaborator = (
        db.query(User)
        .filter(User.id == collaborator_id, User.company_id == current_user.company_id)
        .first()
    )
    if collaborator is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Colaborador não encontrado.",
        )
    return _profile_out(db, _get_or_create_profile(db, collaborator))


@router.put("/collaborators/{collaborator_id}/profile", response_model=ProfileOut)
def update_collaborator_profile(
    collaborator_id: int,
    payload: ProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    """O Capital Humano atualiza a ficha de um colaborador da sua empresa."""
    collaborator = (
        db.query(User)
        .filter(User.id == collaborator_id, User.company_id == current_user.company_id)
        .first()
    )
    if collaborator is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Colaborador não encontrado.",
        )

    profile = _get_or_create_profile(db, collaborator)

    # Validação: número de colaborador único na empresa.
    data = payload.model_dump(exclude_unset=True)
    new_number = data.get("employee_number")
    if new_number:
        clash = (
            db.query(EmployeeProfile)
            .filter(
                EmployeeProfile.company_id == current_user.company_id,
                EmployeeProfile.employee_number == new_number,
                EmployeeProfile.user_id != collaborator.id,
            )
            .first()
        )
        if clash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Já existe um colaborador com este número nesta empresa.",
            )
        data.pop("employee_number", None)

    # Validação: o turno escolhido tem de pertencer à mesma empresa.
    shift_id = data.get("shift_id")
    if shift_id is not None:
        shift = (
            db.query(Shift)
            .filter(Shift.id == shift_id, Shift.company_id == current_user.company_id)
            .first()
        )
        if shift is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Turno não encontrado nesta empresa.",
            )

    for field, value in data.items():
        setattr(profile, field, value)

    db.commit()
    db.refresh(profile)
    return profile


# ---------- Foto do colaborador (CH carrega/modifica/remove) ----------

from fastapi import UploadFile, File, Form
from app.services.cloudinary_upload import upload_file as _cloud_upload

_ALLOWED_PHOTO_EXT = (".jpg", ".jpeg", ".png", ".webp")


@router.post("/collaborators/{collaborator_id}/photo", response_model=ProfileOut)
async def upload_collaborator_photo(
    collaborator_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
    file: UploadFile = File(...),
):
    """O Capital Humano carrega (ou substitui) a foto do colaborador."""
    nome = (file.filename or "")
    ext = nome.lower().rsplit(".", 1)[-1] if "." in nome else ""
    if f".{ext}" not in _ALLOWED_PHOTO_EXT:
        raise HTTPException(
            status_code=422,
            detail="Formato de foto inválido. Use JPG, PNG ou WEBP.",
        )

    collaborator = (
        db.query(User)
        .filter(User.id == collaborator_id, User.company_id == current_user.company_id)
        .first()
    )
    if collaborator is None:
        raise HTTPException(status_code=404, detail="Colaborador não encontrado.")

    profile = _get_or_create_profile(db, collaborator)
    conteudo = await file.read()
    url = _cloud_upload(conteudo, f"foto-{collaborator_id}", folder="kamba/fotos")
    if not url:
        raise HTTPException(
            status_code=502,
            detail="Não foi possível guardar a foto. O armazenamento não está configurado.",
        )

    profile.photo_url = url
    db.commit()
    db.refresh(profile)
    return _profile_out(db, profile)


@router.delete("/collaborators/{collaborator_id}/photo", response_model=ProfileOut)
def delete_collaborator_photo(
    collaborator_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    """O Capital Humano remove a foto do colaborador (volta a mostrar iniciais)."""
    collaborator = (
        db.query(User)
        .filter(User.id == collaborator_id, User.company_id == current_user.company_id)
        .first()
    )
    if collaborator is None:
        raise HTTPException(status_code=404, detail="Colaborador não encontrado.")

    profile = _get_or_create_profile(db, collaborator)
    profile.photo_url = None
    db.commit()
    db.refresh(profile)
    return _profile_out(db, profile)
