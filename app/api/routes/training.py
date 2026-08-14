"""
Rotas do plano de formação (secção 5).

Fluxo:
- CH cria o plano (rascunho) e adiciona ações (origem "área").
- O sistema deteta necessidades a partir das avaliações validadas com nota
  < 3,5 e das ações pendentes dos Planos Individuais de Desenvolvimento
  (rota /needs) e permite gerá-las como ações (origem "sistema").
- CH submete o plano; a Administração aprova. A aprovação passa o plano a
  execução e notifica o CH.
- Em execução, cada ação é acompanhada no portal do colaborador.

Isolamento por company_id.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import settings
from app.models.user import User
from app.models.enums import (
    UserRole, TrainingSource, TrainingPlanStatus, TrainingActionStatus, EvaluationPhase,
)
from app.models.training import TrainingPlan, TrainingAction
from app.models.development import DevelopmentPlan, DevelopmentAction
from app.models.enums import DevelopmentPlanStatus, DevelopmentActionStatus
from app.models.evaluation import Evaluation
from app.schemas.training import (
    PlanCreate, PlanOut, ActionCreate, ActionOut, TrainingNeed,
    ActionStatusUpdate, MyTrainingActionOut,
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


def _get_action_or_404(db: Session, company_id: int, plan_id: int, action_id: int) -> TrainingAction:
    a = (
        db.query(TrainingAction)
        .filter(
            TrainingAction.id == action_id,
            TrainingAction.plan_id == plan_id,
            TrainingAction.company_id == company_id,
        )
        .first()
    )
    if a is None:
        raise HTTPException(status_code=404, detail="Ação de formação não encontrada.")
    return a


def _needs_from_evaluations(db: Session, company_id: int) -> list[TrainingNeed]:
    evals = (
        db.query(Evaluation)
        .filter(
            Evaluation.company_id == company_id,
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
            source="avaliacao",
        ))
    return needs


def _needs_from_pids(db: Session, company_id: int) -> list[TrainingNeed]:
    plans = (
        db.query(DevelopmentPlan)
        .filter(
            DevelopmentPlan.company_id == company_id,
            DevelopmentPlan.status != DevelopmentPlanStatus.CONCLUIDO,
        )
        .all()
    )
    needs = []
    for plan in plans:
        collab = db.query(User).filter(User.id == plan.collaborator_id).first()
        if collab is None:
            continue
        actions = (
            db.query(DevelopmentAction)
            .filter(
                DevelopmentAction.plan_id == plan.id,
                DevelopmentAction.status == DevelopmentActionStatus.PENDENTE,
            )
            .all()
        )
        for a in actions:
            needs.append(TrainingNeed(
                collaborator_id=collab.id,
                collaborator_name=collab.full_name,
                reason=f"PID {plan.year}: {a.title}",
                source="pid",
            ))
    return needs


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
    Sinaliza necessidades a partir das duas fontes do manual:
    - avaliações validadas com nota < 3,5 (fonte 'avaliacao');
    - ações pendentes dos Planos Individuais de Desenvolvimento (fonte 'pid').
    """
    return (
        _needs_from_evaluations(db, current_user.company_id)
        + _needs_from_pids(db, current_user.company_id)
    )


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
    Gera ações automaticamente para as necessidades sinalizadas pelo sistema
    (nota < 3,5 e PID), com origem 'sistema'. Não duplica se já existir ação
    para esse colaborador neste plano com origem sistema.
    """
    plan = _get_plan_or_404(db, current_user.company_id, plan_id)
    if plan.status != TrainingPlanStatus.RASCUNHO:
        raise HTTPException(status_code=409, detail="Só é possível gerar ações num plano em rascunho.")

    needs = _needs_from_evaluations(db, current_user.company_id) + _needs_from_pids(
        db, current_user.company_id
    )

    created = []
    seen = set()
    for need in needs:
        if need.collaborator_id in seen:
            continue
        seen.add(need.collaborator_id)
        exists = (
            db.query(TrainingAction)
            .filter(
                TrainingAction.plan_id == plan.id,
                TrainingAction.collaborator_id == need.collaborator_id,
                TrainingAction.source == TrainingSource.SISTEMA,
            )
            .first()
        )
        if exists:
            continue
        action = TrainingAction(
            company_id=current_user.company_id,
            plan_id=plan.id,
            collaborator_id=need.collaborator_id,
            title="Formação de reforço (sistema)",
            description=need.reason,
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
    """A Administração aprova o plano; passa a execução e notifica o CH."""
    plan = _get_plan_or_404(db, current_user.company_id, plan_id)
    if plan.status != TrainingPlanStatus.SUBMETIDO:
        raise HTTPException(status_code=409, detail="Só um plano submetido pode ser aprovado.")
    plan.status = TrainingPlanStatus.EM_EXECUCAO
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


# ---------- Execução: estado das ações (secção 5) ----------

@router.post("/plans/{plan_id}/actions/{action_id}/status", response_model=ActionOut)
def update_action_status(
    plan_id: int,
    action_id: int,
    payload: ActionStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*CH_ADMIN)),
):
    """O CH acompanha a execução: aprova a ação e marca-a como concluída."""
    plan = _get_plan_or_404(db, current_user.company_id, plan_id)
    if plan.status != TrainingPlanStatus.EM_EXECUCAO:
        raise HTTPException(status_code=409, detail="Só é possível gerir ações num plano em execução.")
    action = _get_action_or_404(db, current_user.company_id, plan_id, action_id)
    action.status = payload.status
    db.commit()
    db.refresh(action)
    return action


@router.get("/my-actions", response_model=list[MyTrainingActionOut])
def my_actions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """As ações de formação do próprio colaborador, para acompanhar no portal."""
    rows = (
        db.query(TrainingAction, TrainingPlan)
        .join(TrainingPlan, TrainingPlan.id == TrainingAction.plan_id)
        .filter(
            TrainingAction.company_id == current_user.company_id,
            TrainingAction.collaborator_id == current_user.id,
        )
        .order_by(TrainingAction.created_at.desc())
        .all()
    )
    return [
        MyTrainingActionOut(
            id=a.id, plan_id=p.id, plan_name=p.name,
            title=a.title, description=a.description,
            source=a.source, status=a.status, created_at=a.created_at,
        )
        for a, p in rows
    ]


# ---------- Catálogo CLACS Academy (secção 5) ----------

@router.get("/academy-catalog")
def academy_catalog():
    """Ligação ao catálogo da CLACS Academy (configurável por env)."""
    return {
        "url": settings.CLACS_ACADEMY_URL,
        "integrado": bool(settings.CLACS_ACADEMY_URL),
    }
