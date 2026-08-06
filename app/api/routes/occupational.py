"""
Rotas de Saúde Ocupacional (secção 2.7).
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.models.enums import UserRole
from app.models.occupational import OccupationalExam
from app.schemas.occupational import ExamCreate, ExamOut, OverdueExam
from app.api.deps import get_current_user, require_roles

router = APIRouter(prefix="/occupational-health", tags=["occupational_health"])

MANAGE_ROLES = (UserRole.CAPITAL_HUMANO, UserRole.ADMINISTRACAO)


@router.post("/exams", response_model=ExamOut, status_code=status.HTTP_201_CREATED)
def register_exam(
    payload: ExamCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    collab = (
        db.query(User)
        .filter(User.id == payload.collaborator_id, User.company_id == current_user.company_id)
        .first()
    )
    if collab is None:
        raise HTTPException(status_code=404, detail="Colaborador não encontrado nesta empresa.")

    exam = OccupationalExam(
        company_id=current_user.company_id,
        collaborator_id=payload.collaborator_id,
        fitness=payload.fitness,
        exam_date=payload.exam_date,
        next_exam_date=payload.next_exam_date,
        restriction_note=payload.restriction_note,
    )
    db.add(exam)
    db.commit()
    db.refresh(exam)
    return exam


@router.get("/collaborators/{collaborator_id}/exams", response_model=list[ExamOut])
def list_collaborator_exams(
    collaborator_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    collab = (
        db.query(User)
        .filter(User.id == collaborator_id, User.company_id == current_user.company_id)
        .first()
    )
    if collab is None:
        raise HTTPException(status_code=404, detail="Colaborador não encontrado nesta empresa.")
    return (
        db.query(OccupationalExam)
        .filter(OccupationalExam.collaborator_id == collaborator_id)
        .order_by(OccupationalExam.exam_date.desc())
        .all()
    )


@router.get("/me/exams", response_model=list[ExamOut])
def my_exams(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(OccupationalExam)
        .filter(OccupationalExam.collaborator_id == current_user.id)
        .order_by(OccupationalExam.exam_date.desc())
        .all()
    )


@router.get("/overdue", response_model=list[OverdueExam])
def overdue_exams(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    today = date.today()

    exams = (
        db.query(OccupationalExam)
        .filter(
            OccupationalExam.company_id == current_user.company_id,
            OccupationalExam.next_exam_date.isnot(None),
            OccupationalExam.next_exam_date < today,
        )
        .all()
    )

    latest_by_collab: dict[int, OccupationalExam] = {}
    for e in exams:
        cur = latest_by_collab.get(e.collaborator_id)
        if cur is None or e.exam_date > cur.exam_date:
            latest_by_collab[e.collaborator_id] = e

    result = []
    for collab_id, e in latest_by_collab.items():
        collab = db.query(User).filter(User.id == collab_id).first()
        if collab is None:
            continue
        result.append(OverdueExam(
            collaborator_id=collab_id,
            collaborator_name=collab.full_name,
            last_exam_date=e.exam_date,
            next_exam_date=e.next_exam_date,
            days_overdue=(today - e.next_exam_date).days,
        ))
    return result