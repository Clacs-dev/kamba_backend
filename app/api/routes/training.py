"""
Rotas do plano de formação (secção 5).

Fluxo:
- CH cria o plano (rascunho) e adiciona ações (origem "área").
- O sistema deteta necessidades a partir das avaliações validadas com nota
  < 3,5 (rota /needs) e permite gerá-las como ações (origem "sistema").
- CH submete o plano; a Administração aprova. A aprovação passa o plano a
  execução.

Isolamento por company_id.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.models.enums import (
    UserRole, TrainingSource, TrainingPlanStatus, TrainingActionStatus, EvaluationPhase,
)
from app.models.training import TrainingPlan, TrainingAction
from app.models.evaluation import Evaluation
from app.schemas.training import (
    PlanCreate, PlanOut, ActionCreate, ActionOut, TrainingNeed,
)
from app.api.deps import get_current_user, require_roles
from app.services.notifications import notify
from app.services.audit import audit

router = APIRouter(prefix="/training", tags=["training"])

MANAGE_ROLES = (UserRole.CAPITAL_HUMANO, UserRole.ADMINISTRACAO, UserRole.DIRECTOR)
CH_ADMIN = (UserRole.CAPITAL_HUMANO, UserRole.ADMINISTRACAO)

SCORE_THRESHOLD = 3.5  # abaixo disto, o sistema sinaliza necessidade (secção 5)


def _get_plan_or_404(db: Session, company_id: int, plan_id: int) -> TrainingPlan:
    p = (
        db.query(TrainingPlan)
        .filter(TrainingPlan.id == plan_id, TrainingPlan.company_id == company_id)
        .first()
    )
    if p is None:
        raise HTTPException(status_code=404, detail="Plano não encontrado.")
    return p


# ---------- Planos ----------

@router.post("/plans", response_model=PlanOut, status_code=status.HTTP_201_CREATED)
def create_plan(
    payload: PlanCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*CH_ADMIN)),
):
    plan = TrainingPlan(company_id=current_user.company_id, name=payload.name)
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


@router.get("/plans", response_model=list[PlanOut])
def list_plans(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(TrainingPlan)
        .filter(TrainingPlan.company_id == current_user.company_id)
        .order_by(TrainingPlan.created_at.desc())
        .all()
    )


# ---------- Deteção automática de necessidades (secção 5) ----------

@router.get("/needs", response_model=list[TrainingNeed])
def detect_needs(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*CH_ADMIN)),
):
    """
    Sinaliza colaboradores com nota da última avaliação validada < 3,5.
    Esta é a fonte 'necessidades identificadas pelo sistema'.
    """
    evals = (
        db.query(Evaluation)
        .filter(
            Evaluation.company_id == current_user.company_id,
            Evaluation.phase == EvaluationPhase.VALIDADA,
            Evaluation.final_score.isnot(None),
            Evaluation.final_score < SCORE_THRESHOLD,
        )
        .all()
    )

    needs = []
    for ev in evals:
        collab = db.query(User).filter(User.id == ev.collaborator_id).first()
        if collab is None:
            continue
        needs.append(TrainingNeed(
            collaborator_id=collab.id,
            collaborator_name=collab.full_name,
            last_score=ev.final_score,
            classification=ev.classification,
            reason=f"Nota {ev.final_score} ({ev.classification}) abaixo de {SCORE_THRESHOLD}.",
        ))
    return needs


# ---------- Ações ----------

@router.post("/plans/{plan_id}/actions", response_model=ActionOut, status_code=status.HTTP_201_CREATED)
def add_action(
    plan_id: int,
    payload: ActionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    """Adiciona uma ação formativa indicada pela área (origem 'área')."""
    plan = _get_plan_or_404(db, current_user.company_id, plan_id)
    if plan.status not in (TrainingPlanStatus.RASCUNHO,):
        raise HTTPException(status_code=409, detail="Só é possível adicionar ações a um plano em rascunho.")

    collab = (
        db.query(User)
        .filter(User.id == payload.collaborator_id, User.company_id == current_user.company_id)
        .first()
    )
    if collab is None:
        raise HTTPException(status_code=404, detail="Colaborador não encontrado nesta empresa.")

    action = TrainingAction(
        company_id=current_user.company_id,
        plan_id=plan.id,
        collaborator_id=payload.collaborator_id,
        title=payload.title,
        description=payload.description,
        source=TrainingSource.AREA,
    )
    db.add(action)
    db.commit()
    db.refresh(action)
    return action


@router.post("/plans/{plan_id}/actions/from-needs", response_model=list[ActionOut])
def generate_actions_from_needs(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*CH_ADMIN)),
):
    """
    Gera ações automaticamente para os colaboradores sinalizados pelo sistema
    (nota < 3,5), com origem 'sistema'. Não duplica se já existir ação para
    esse colaborador neste plano com origem sistema.
    """
    plan = _get_plan_or_404(db, current_user.company_id, plan_id)
    if plan.status != TrainingPlanStatus.RASCUNHO:
        raise HTTPException(status_code=409, detail="Só é possível gerar ações num plano em rascunho.")

    evals = (
        db.query(Evaluation)
        .filter(
            Evaluation.company_id == current_user.company_id,
            Evaluation.phase == EvaluationPhase.VALIDADA,
            Evaluation.final_score.isnot(None),
            Evaluation.final_score < SCORE_THRESHOLD,
        )
        .all()
    )

    created = []
    for ev in evals:
        exists = (
            db.query(TrainingAction)
            .filter(
                TrainingAction.plan_id == plan.id,
                TrainingAction.collaborator_id == ev.collaborator_id,
                TrainingAction.source == TrainingSource.SISTEMA,
            )
            .first()
        )
        if exists:
            continue
        action = TrainingAction(
            company_id=current_user.company_id,
            plan_id=plan.id,
            collaborator_id=ev.collaborator_id,
            title="Formação de reforço (nota baixa)",
            description=f"Gerada automaticamente. Nota {ev.final_score} ({ev.classification}).",
            source=TrainingSource.SISTEMA,
        )
        db.add(action)
        created.append(action)

    db.commit()
    for a in created:
        db.refresh(a)
    return created


@router.get("/plans/{plan_id}/actions", response_model=list[ActionOut])
def list_actions(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plan = _get_plan_or_404(db, current_user.company_id, plan_id)
    return (
        db.query(TrainingAction)
        .filter(TrainingAction.plan_id == plan.id)
        .order_by(TrainingAction.created_at)
        .all()
    )


# ---------- Fluxo de aprovação ----------

@router.post("/plans/{plan_id}/submit", response_model=PlanOut)
def submit_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*CH_ADMIN)),
):
    """CH submete o plano à Administração."""
    plan = _get_plan_or_404(db, current_user.company_id, plan_id)
    if plan.status != TrainingPlanStatus.RASCUNHO:
        raise HTTPException(status_code=409, detail="Só um plano em rascunho pode ser submetido.")
    plan.status = TrainingPlanStatus.SUBMETIDO
    db.commit()
    db.refresh(plan)
    return plan


@router.post("/plans/{plan_id}/approve", response_model=PlanOut)
def approve_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMINISTRACAO)),
):
    """A Administração aprova o plano; passa a execução."""
    plan = _get_plan_or_404(db, current_user.company_id, plan_id)
    if plan.status != TrainingPlanStatus.SUBMETIDO:
        raise HTTPException(status_code=409, detail="Só um plano submetido pode ser aprovado.")
    plan.status = TrainingPlanStatus.APROVADO
    # O manual: a aprovação gera notificação ao Capital Humano para execução.
    chs = (
        db.query(User)
        .filter(User.company_id == plan.company_id, User.role == UserRole.CAPITAL_HUMANO)
        .all()
    )
    for ch in chs:
        notify(
            db, company_id=plan.company_id, user_id=ch.id,
            title="Plano de formação aprovado",
            message=f"O plano '{plan.name}' foi aprovado pela Administração. Pode iniciar a execução.",
            category="formacao", link=f"/training/plans/{plan.id}",
        )
    audit(db, actor=current_user, action="formacao.plano_aprovado",
          detail=f"Plano de formação '{plan.name}' aprovado.")
    db.commit()
    db.refresh(plan)
    return plan
