"""
Rotas de Remuneração e Assiduidade (secção 2.8).
Visibilidade: próprio, Capital Humano e Administração.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.models.enums import UserRole
from app.models.compensation import SalaryRecord, AttendanceRecord
from app.schemas.compensation import (
    SalaryCreate, SalaryOut, AttendanceCreate, AttendanceOut,
)
from app.api.deps import get_current_user, require_roles

router = APIRouter(prefix="/compensation", tags=["compensation"])

MANAGE_ROLES = (UserRole.CAPITAL_HUMANO, UserRole.ADMINISTRACAO)


def _can_view(current_user: User, collaborator_id: int) -> bool:
    if current_user.id == collaborator_id:
        return True
    return current_user.role in MANAGE_ROLES


def _collab_in_company_or_404(db: Session, company_id: int, collaborator_id: int) -> User:
    collab = (
        db.query(User)
        .filter(User.id == collaborator_id, User.company_id == company_id)
        .first()
    )
    if collab is None:
        raise HTTPException(status_code=404, detail="Colaborador não encontrado nesta empresa.")
    return collab


@router.post("/salary", response_model=SalaryOut, status_code=status.HTTP_201_CREATED)
def add_salary(
    payload: SalaryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    _collab_in_company_or_404(db, current_user.company_id, payload.collaborator_id)
    rec = SalaryRecord(
        company_id=current_user.company_id,
        collaborator_id=payload.collaborator_id,
        year=payload.year,
        gross_salary=payload.gross_salary,
        salary_grade=payload.salary_grade,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


@router.get("/collaborators/{collaborator_id}/salary", response_model=list[SalaryOut])
def list_salary(
    collaborator_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _can_view(current_user, collaborator_id):
        raise HTTPException(status_code=403, detail="Sem acesso a estes dados.")
    _collab_in_company_or_404(db, current_user.company_id, collaborator_id)
    return (
        db.query(SalaryRecord)
        .filter(
            SalaryRecord.company_id == current_user.company_id,
            SalaryRecord.collaborator_id == collaborator_id,
        )
        .order_by(SalaryRecord.year)
        .all()
    )


@router.post("/attendance", response_model=AttendanceOut, status_code=status.HTTP_201_CREATED)
def add_attendance(
    payload: AttendanceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    _collab_in_company_or_404(db, current_user.company_id, payload.collaborator_id)
    rec = AttendanceRecord(
        company_id=current_user.company_id,
        collaborator_id=payload.collaborator_id,
        period=payload.period,
        present_days=payload.present_days,
        justified_absences=payload.justified_absences,
        unjustified_absences=payload.unjustified_absences,
        vacation_days_taken=payload.vacation_days_taken,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


@router.get("/collaborators/{collaborator_id}/attendance", response_model=list[AttendanceOut])
def list_attendance(
    collaborator_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _can_view(current_user, collaborator_id):
        raise HTTPException(status_code=403, detail="Sem acesso a estes dados.")
    _collab_in_company_or_404(db, current_user.company_id, collaborator_id)
    return (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.company_id == current_user.company_id,
            AttendanceRecord.collaborator_id == collaborator_id,
        )
        .order_by(AttendanceRecord.period)
        .all()
    )


@router.get("/me/salary", response_model=list[SalaryOut])
def my_salary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(SalaryRecord)
        .filter(SalaryRecord.collaborator_id == current_user.id)
        .order_by(SalaryRecord.year)
        .all()
    )


@router.get("/me/attendance", response_model=list[AttendanceOut])
def my_attendance(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.collaborator_id == current_user.id)
        .order_by(AttendanceRecord.period)
        .all()
    )