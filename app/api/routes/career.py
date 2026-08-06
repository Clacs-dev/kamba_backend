"""
Rotas do Percurso / linha do tempo (secção 2.3).
Agrega numa só linha do tempo: eventos manuais + admissão + avaliações
validadas + processos disciplinares arquivados + exames + formações.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.models.enums import UserRole, EvaluationPhase, DisciplinaryPhase
from app.models.career import CareerEvent
from app.models.employee_profile import EmployeeProfile
from app.models.evaluation import Evaluation
from app.models.disciplinary import DisciplinaryProcess
from app.models.occupational import OccupationalExam
from app.models.training import TrainingAction
from app.schemas.career import CareerEventCreate, CareerEventOut, TimelineItem
from app.api.deps import get_current_user, require_roles

router = APIRouter(prefix="/career", tags=["career"])

MANAGE_ROLES = (UserRole.CAPITAL_HUMANO, UserRole.ADMINISTRACAO)


def _can_view(current_user: User, collaborator_id: int) -> bool:
    return current_user.id == collaborator_id or current_user.role in MANAGE_ROLES


@router.post("/events", response_model=CareerEventOut, status_code=status.HTTP_201_CREATED)
def add_event(
    payload: CareerEventCreate,
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

    ev = CareerEvent(
        company_id=current_user.company_id,
        collaborator_id=payload.collaborator_id,
        event_type=payload.event_type,
        event_date=payload.event_date,
        title=payload.title,
        description=payload.description,
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev


@router.get("/collaborators/{collaborator_id}/timeline", response_model=list[TimelineItem])
def timeline(
    collaborator_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _can_view(current_user, collaborator_id):
        raise HTTPException(status_code=403, detail="Sem acesso a este percurso.")

    company_id = current_user.company_id
    collab = (
        db.query(User)
        .filter(User.id == collaborator_id, User.company_id == company_id)
        .first()
    )
    if collab is None:
        raise HTTPException(status_code=404, detail="Colaborador não encontrado nesta empresa.")

    items: list[TimelineItem] = []

    for e in db.query(CareerEvent).filter(
        CareerEvent.company_id == company_id,
        CareerEvent.collaborator_id == collaborator_id,
    ).all():
        items.append(TimelineItem(
            date=e.event_date, source="manual", category=e.event_type.value,
            title=e.title, detail=e.description,
        ))

    profile = db.query(EmployeeProfile).filter(
        EmployeeProfile.user_id == collaborator_id
    ).first()
    if profile and profile.admission_date:
        items.append(TimelineItem(
            date=profile.admission_date, source="ficha", category="admissao",
            title="Admissão", detail=None,
        ))

    for ev in db.query(Evaluation).filter(
        Evaluation.company_id == company_id,
        Evaluation.collaborator_id == collaborator_id,
        Evaluation.phase == EvaluationPhase.VALIDADA,
    ).all():
        items.append(TimelineItem(
            date=ev.updated_at.date(), source="avaliacao", category="avaliacao_homologada",
            title=f"Avaliação homologada — {ev.classification or ''}".strip(),
            detail=f"Pontuação: {ev.final_score}" if ev.final_score is not None else None,
        ))

    for p in db.query(DisciplinaryProcess).filter(
        DisciplinaryProcess.company_id == company_id,
        DisciplinaryProcess.accused_id == collaborator_id,
        DisciplinaryProcess.phase == DisciplinaryPhase.ARQUIVADO,
    ).all():
        items.append(TimelineItem(
            date=p.updated_at.date(), source="disciplina", category="processo_disciplinar",
            title=f"Processo disciplinar concluído ({p.reference})",
            detail=f"Resultado: {p.outcome.value}",
        ))

    for ex in db.query(OccupationalExam).filter(
        OccupationalExam.company_id == company_id,
        OccupationalExam.collaborator_id == collaborator_id,
    ).all():
        items.append(TimelineItem(
            date=ex.exam_date, source="saude", category="exame",
            title=f"Exame de medicina no trabalho — {ex.fitness.value}", detail=None,
        ))

    for ta in db.query(TrainingAction).filter(
        TrainingAction.company_id == company_id,
        TrainingAction.collaborator_id == collaborator_id,
    ).all():
        items.append(TimelineItem(
            date=ta.created_at.date(), source="formacao", category="formacao",
            title=f"Formação: {ta.title}", detail=ta.description,
        ))

    items.sort(key=lambda i: i.date, reverse=True)
    return items


@router.get("/me/timeline", response_model=list[TimelineItem])
def my_timeline(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return timeline(current_user.id, db, current_user)