"""
Rota do Dashboard (métricas agregadas da empresa).
Reservado a Capital Humano e Administração. Usa contagens na base de dados.
"""
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.models.enums import UserRole, EvaluationPhase, DisciplinaryPhase
from app.models.evaluation import Evaluation
from app.models.disciplinary import DisciplinaryProcess
from app.models.training import TrainingPlan, TrainingAction
from app.models.occupational import OccupationalExam
from app.schemas.dashboard import (
    DashboardSummary, CollaboratorsMetrics, EvaluationMetrics,
    DisciplinaryMetrics, TrainingMetrics, HealthMetrics,
)
from app.api.deps import require_roles

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

MANAGE_ROLES = (UserRole.CAPITAL_HUMANO, UserRole.ADMINISTRACAO)
SCORE_THRESHOLD = 3.5


@router.get("/summary", response_model=DashboardSummary)
def summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    cid = current_user.company_id

    total_collabs = db.query(func.count(User.id)).filter(User.company_id == cid).scalar() or 0
    active_collabs = db.query(func.count(User.id)).filter(
        User.company_id == cid, User.is_active == True  # noqa: E712
    ).scalar() or 0
    by_role_rows = (
        db.query(User.role, func.count(User.id))
        .filter(User.company_id == cid)
        .group_by(User.role)
        .all()
    )
    by_role = {role.value: count for role, count in by_role_rows}

    collaborators = CollaboratorsMetrics(
        total=total_collabs,
        active=active_collabs,
        inactive=total_collabs - active_collabs,
        by_role=by_role,
    )

    total_evals = db.query(func.count(Evaluation.id)).filter(Evaluation.company_id == cid).scalar() or 0
    validated = db.query(func.count(Evaluation.id)).filter(
        Evaluation.company_id == cid, Evaluation.phase == EvaluationPhase.VALIDADA
    ).scalar() or 0
    in_progress_evals = db.query(func.count(Evaluation.id)).filter(
        Evaluation.company_id == cid,
        Evaluation.phase.notin_([EvaluationPhase.VALIDADA, EvaluationPhase.FECHADA]),
    ).scalar() or 0
    below = db.query(func.count(Evaluation.id)).filter(
        Evaluation.company_id == cid,
        Evaluation.phase == EvaluationPhase.VALIDADA,
        Evaluation.final_score.isnot(None),
        Evaluation.final_score < SCORE_THRESHOLD,
    ).scalar() or 0
    class_rows = (
        db.query(Evaluation.classification, func.count(Evaluation.id))
        .filter(Evaluation.company_id == cid, Evaluation.classification.isnot(None))
        .group_by(Evaluation.classification)
        .all()
    )
    by_classification = {c: n for c, n in class_rows}

    evaluations = EvaluationMetrics(
        total=total_evals,
        in_progress=in_progress_evals,
        validated=validated,
        below_threshold=below,
        by_classification=by_classification,
    )

    total_disc = db.query(func.count(DisciplinaryProcess.id)).filter(
        DisciplinaryProcess.company_id == cid
    ).scalar() or 0
    archived = db.query(func.count(DisciplinaryProcess.id)).filter(
        DisciplinaryProcess.company_id == cid,
        DisciplinaryProcess.phase == DisciplinaryPhase.ARQUIVADO,
    ).scalar() or 0

    disciplinary = DisciplinaryMetrics(
        total=total_disc,
        in_progress=total_disc - archived,
        archived=archived,
    )

    plans = db.query(func.count(TrainingPlan.id)).filter(TrainingPlan.company_id == cid).scalar() or 0
    actions = db.query(func.count(TrainingAction.id)).filter(TrainingAction.company_id == cid).scalar() or 0
    training = TrainingMetrics(plans=plans, actions=actions)

    exams = db.query(func.count(OccupationalExam.id)).filter(
        OccupationalExam.company_id == cid
    ).scalar() or 0
    overdue = db.query(func.count(OccupationalExam.id)).filter(
        OccupationalExam.company_id == cid,
        OccupationalExam.next_exam_date.isnot(None),
        OccupationalExam.next_exam_date < date.today(),
    ).scalar() or 0
    health = HealthMetrics(exams=exams, overdue=overdue)

    return DashboardSummary(
        collaborators=collaborators,
        evaluations=evaluations,
        disciplinary=disciplinary,
        training=training,
        health=health,
    )