"""
Rotas da ficha do colaborador (secção 2.1).
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.models.enums import UserRole
from app.models.employee_profile import EmployeeProfile
from app.schemas.profile import ProfileUpdate, ProfileOut
from app.api.deps import get_current_user, require_roles

router = APIRouter(tags=["profiles"])

MANAGE_ROLES = (UserRole.CAPITAL_HUMANO, UserRole.ADMINISTRACAO)


def _get_or_create_profile(db: Session, user: User) -> EmployeeProfile:
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


@router.get("/me/profile", response_model=ProfileOut)
def get_my_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _get_or_create_profile(db, current_user)


@router.get("/collaborators/{collaborator_id}/profile", response_model=ProfileOut)
def get_collaborator_profile(
    collaborator_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    collaborator = (
        db.query(User)
        .filter(User.id == collaborator_id, User.company_id == current_user.company_id)
        .first()
    )
    if collaborator is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Colaborador não encontrado.")
    return _get_or_create_profile(db, collaborator)


@router.put("/collaborators/{collaborator_id}/profile", response_model=ProfileOut)
def update_collaborator_profile(
    collaborator_id: int,
    payload: ProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    collaborator = (
        db.query(User)
        .filter(User.id == collaborator_id, User.company_id == current_user.company_id)
        .first()
    )
    if collaborator is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Colaborador não encontrado.")

    profile = _get_or_create_profile(db, collaborator)

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
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Já existe um colaborador com este número nesta empresa.")

    for field, value in data.items():
        setattr(profile, field, value)

    db.commit()
    db.refresh(profile)
    return profile