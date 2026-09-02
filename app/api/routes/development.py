"""
Rotas dos Planos Individuais de Desenvolvimento (PID) — secção 5.

- CH / Administração / Director criam e listam os PIDs da empresa.
- O colaborador vê apenas o seu PID.
- Concluir ações: o próprio colaborador (no seu portal) ou os gestores.
  Quando todas as ações estão concluídas, o PID passa a 'concluido'.

Isolamento por company_id.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.models.enums import UserRole, DevelopmentPlanStatus, DevelopmentActionStatus
from app.models.development import DevelopmentPlan, DevelopmentAction
from app.schemas.development import (
    DevelopmentPlanCreate, DevelopmentPlanOut, DevelopmentActionOut,
)
from app.api.deps import get_current_user, require_roles
from app.services.audit import audit

router = APIRouter(prefix="/development-plans", tags=["development"])

MANAGE_ROLES = (UserRole.CAPITAL_HUMANO, UserRole.ADMINISTRACAO, UserRole.DIRECTOR, UserRole.ADMIN)


def _get_plan_or_404(db: Session, company_id: int, plan_id: int) -> DevelopmentPlan:
    p = (
        db.query(DevelopmentPlan)
        .filter(DevelopmentPlan.id == plan_id, DevelopmentPlan.company_id == company_id)
        .first()
    )
    if p is None:
        raise HTTPException(status_code=404, detail="PID não encontrado.")
    return p


def _serialize(db: Session, plan: DevelopmentPlan) -> DevelopmentPlanOut:
    collab = db.query(User).filter(User.id == plan.collaborator_id).first()
    actions = (
        db.query(DevelopmentAction)
        .filter(DevelopmentAction.plan_id == plan.id)
        .order_by(DevelopmentAction.id)
        .all()
    )
    out = DevelopmentPlanOut.model_validate(plan)
    out.collaborator_name = collab.full_name if collab else None
    out.actions = [DevelopmentActionOut.model_validate(a) for a in actions]
    return out


@router.post("", response_model=DevelopmentPlanOut, status_code=status.HTTP_201_CREATED)
def create_plan(
    payload: DevelopmentPlanCreate,
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

    plan = DevelopmentPlan(
        company_id=current_user.company_id,
        collaborator_id=payload.collaborator_id,
        year=payload.year,
        created_by=current_user.id,
    )
    db.add(plan)
    db.flush()

    for a in payload.actions:
        db.add(DevelopmentAction(
            company_id=current_user.company_id,
            plan_id=plan.id,
            title=a.title,
            description=a.description,
        ))

    db.commit()
    audit(db, actor=current_user, action="formacao.pid_criado",
          detail=f"PID {plan.year} criado para {collab.full_name} ({len(payload.actions)} ações).")
    db.refresh(plan)
    return _serialize(db, plan)


@router.get("", response_model=list[DevelopmentPlanOut])
def list_plans(
    collaborator_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(DevelopmentPlan).filter(
        DevelopmentPlan.company_id == current_user.company_id
    )
    if collaborator_id is not None and current_user.role in MANAGE_ROLES:
        query = query.filter(DevelopmentPlan.collaborator_id == collaborator_id)
    elif current_user.role not in MANAGE_ROLES:
        query = query.filter(DevelopmentPlan.collaborator_id == current_user.id)
    plans = query.order_by(DevelopmentPlan.created_at.desc()).all()
    return [_serialize(db, p) for p in plans]


@router.get("/{plan_id}", response_model=DevelopmentPlanOut)
def get_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = _get_plan_or_404(db, current_user.company_id, plan_id)
    if current_user.role not in MANAGE_ROLES and p.collaborator_id != current_user.id:
        raise HTTPException(status_code=403, detail="Sem acesso a este PID.")
    return _serialize(db, p)


@router.post("/{plan_id}/actions/{action_id}/complete", response_model=DevelopmentPlanOut)
def complete_action(
    plan_id: int,
    action_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = _get_plan_or_404(db, current_user.company_id, plan_id)
    if current_user.role not in MANAGE_ROLES and p.collaborator_id != current_user.id:
        raise HTTPException(status_code=403, detail="Sem acesso a este PID.")

    action = (
        db.query(DevelopmentAction)
        .filter(DevelopmentAction.id == action_id, DevelopmentAction.plan_id == p.id)
        .first()
    )
    if action is None:
        raise HTTPException(status_code=404, detail="Ação de desenvolvimento não encontrada.")

    action.status = DevelopmentActionStatus.CONCLUIDA
    db.flush()

    remaining = (
        db.query(DevelopmentAction)
        .filter(
            DevelopmentAction.plan_id == p.id,
            DevelopmentAction.status == DevelopmentActionStatus.PENDENTE,
        )
        .count()
    )
    if remaining == 0:
        p.status = DevelopmentPlanStatus.CONCLUIDO

    db.commit()
    audit(db, actor=current_user, action="formacao.pid_acao_concluida",
          detail=f"Ação '{action.title}' concluída no PID do colaborador {p.collaborator_id}.")
    db.refresh(p)
    return _serialize(db, p)
