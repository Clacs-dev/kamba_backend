"""
Rotas do módulo Administração (equivalente ao módulo "admin" do protótipo).

Acesso: Capital Humano e Administração (no protótipo o módulo é visível a CH e CE).
Reúne num só GET: dados da empresa (plano SaaS), parâmetros do ciclo e a
trilha de auditoria recente — para a página "Administração" do frontend.
Permite ainda gerir o plano de subscrição.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.models.enums import UserRole
from app.models.company import Company
from app.models.audit import AuditEvent
from app.api.deps import require_roles
from app.api.routes.evaluation_settings import get_or_create_settings
from app.services.audit import audit

router = APIRouter(prefix="/admin", tags=["admin"])

ADMIN_ROLES = (UserRole.CAPITAL_HUMANO, UserRole.ADMINISTRACAO, UserRole.ADMIN)

# Planos de subscrição disponíveis (secção 10 do manual).
PLANOS_VALIDOS = {"essencial", "empresarial", "corporativo", "institucional"}


class PlanUpdate(BaseModel):
    plan: str = Field(..., min_length=2, max_length=50)


class ShiftsToggle(BaseModel):
    uses_shifts: bool


@router.get("/overview")
def admin_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    cid = current_user.company_id
    company = db.query(Company).filter(Company.id == cid).first()

    settings = get_or_create_settings(db, cid)

    # Contagem de colaboradores da empresa (para o "Plano SaaS").
    user_count = (
        db.query(User).filter(User.company_id == cid, User.is_active == True).count()  # noqa: E712
    )

    audit_rows = (
        db.query(AuditEvent)
        .filter(AuditEvent.company_id == cid)
        .order_by(AuditEvent.created_at.desc())
        .limit(12)
        .all()
    )

    return {
        "company": {
            "id": company.id if company else None,
            "name": company.name if company else "",
            "nif": company.nif if company else None,
            "plan": company.plan if company else "essencial",
            "is_active": company.is_active if company else True,
            "user_count": user_count,
            "uses_shifts": company.uses_shifts if company else False,
        },
        "settings": {
            "tec_objectives": round(settings.tec_objectives * 100),
            "tec_competencies": round(settings.tec_competencies * 100),
            "tec_values": round(settings.tec_values * 100),
            "dir_objectives": round(settings.dir_objectives * 100),
            "dir_competencies": round(settings.dir_competencies * 100),
            "dir_values": round(settings.dir_values * 100),
            "appeal_deadline_days": settings.appeal_deadline_days,
            "cycle_calendar": settings.cycle_calendar,
        },
        "audit": [
            {
                "id": a.id,
                "actor_name": a.actor_name,
                "actor_role": a.actor_role,
                "action": a.action,
                "detail": a.detail,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in audit_rows
        ],
    }


@router.put("/company/plan")
def update_company_plan(
    payload: PlanUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """Gestão do plano de subscrição (secção 10). Fica registado na auditoria."""
    if payload.plan not in PLANOS_VALIDOS:
        raise HTTPException(status_code=422, detail=f"Plano inválido. Use um de: {', '.join(sorted(PLANOS_VALIDOS))}.")

    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    if company is None:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")

    anterior = company.plan
    company.plan = payload.plan
    audit(db, actor=current_user, action="admin.plano_alterado",
          detail=f"Plano de subscrição alterado: {anterior} → {payload.plan}.")
    db.commit()
    return {"plan": company.plan, "anterior": anterior}


@router.put("/company/shifts")
def toggle_company_shifts(
    payload: ShiftsToggle,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """
    Liga/desliga o regime de turnos da empresa (alteração 9). Com o regime
    desligado, os colaboradores continuam a poder usar horário fixo; só deixa
    de fazer sentido associá-los a um turno novo.
    """
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    if company is None:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")

    anterior = company.uses_shifts
    company.uses_shifts = payload.uses_shifts
    audit(db, actor=current_user, action="admin.turnos_alterado",
          detail=f"Regime de turnos: {anterior} → {payload.uses_shifts}.")
    db.commit()
    return {"uses_shifts": company.uses_shifts}
