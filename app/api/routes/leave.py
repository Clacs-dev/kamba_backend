"""
Rotas de Férias & Ausências.

Fluxo de aprovação:
  colaborador cria -> PENDENTE_DIRECTOR
  director aprova   -> PENDENTE_CH   (ou RECUSADA)
  Capital Humano averba -> APROVADA  (ou RECUSADA)

Saldo de férias: 22 dias por ano (secção do módulo). O saldo do ano em curso é
22 menos os dias de férias já aprovados nesse ano.
Cada transição notifica quem tem de agir a seguir (ou o colaborador na decisão).
"""
from datetime import datetime, timezone, date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.models.enums import UserRole, LeaveType, LeaveStatus
from app.models.leave import LeaveRequest
from app.api.deps import get_current_user, require_roles
from app.services.notifications import notify

router = APIRouter(prefix="/leave", tags=["leave"])

ANNUAL_ALLOWANCE = 22  # dias de férias por ano
CH_ROLES = (UserRole.CAPITAL_HUMANO, UserRole.ADMINISTRACAO)


# ---------- Schemas ----------

class LeaveIn(BaseModel):
    leave_type: LeaveType
    start_date: date
    end_date: date
    reason: str | None = Field(default=None, max_length=1000)
    document_name: str | None = Field(default=None, max_length=255)
    document_url: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _datas(self):
        if self.end_date < self.start_date:
            raise ValueError("A data de fim não pode ser anterior à data de início.")
        return self


class LeaveDecision(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


class LeaveOut(BaseModel):
    id: int
    collaborator_id: int
    leave_type: LeaveType
    start_date: date
    end_date: date
    days: int
    reason: str | None
    document_name: str | None
    document_url: str | None
    status: LeaveStatus
    decision_note: str | None
    model_config = {"from_attributes": True}


class BalanceOut(BaseModel):
    year: int
    allowance: int
    used: int
    remaining: int


# ---------- Helpers ----------

def _count_days(a: date, b: date) -> int:
    """Número de dias corridos entre duas datas, inclusive."""
    return (b - a).days + 1


def _get_or_404(db: Session, company_id: int, req_id: int) -> LeaveRequest:
    r = (
        db.query(LeaveRequest)
        .filter(LeaveRequest.id == req_id, LeaveRequest.company_id == company_id)
        .first()
    )
    if not r:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")
    return r


# ---------- Criar ----------

@router.post("", response_model=LeaveOut, status_code=201)
def create_leave(
    payload: LeaveIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """O colaborador submete um pedido de ausência."""
    req = LeaveRequest(
        company_id=current_user.company_id,
        collaborator_id=current_user.id,
        leave_type=payload.leave_type,
        start_date=payload.start_date,
        end_date=payload.end_date,
        days=_count_days(payload.start_date, payload.end_date),
        reason=payload.reason,
        document_name=payload.document_name,
        document_url=payload.document_url,
        status=LeaveStatus.PENDENTE_DIRECTOR,
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    # Notifica os directores da empresa.
    directores = (
        db.query(User)
        .filter(User.company_id == current_user.company_id, User.role == UserRole.DIRECTOR)
        .all()
    )
    for d in directores:
        notify(
            db, company_id=current_user.company_id, user_id=d.id,
            title="Pedido de ausência para aprovar",
            message=f"{current_user.full_name} submeteu um pedido de {payload.leave_type.value}.",
            category="ausencia", link="/ausencias",
        )
    db.commit()
    return req


# ---------- Listar ----------

@router.get("/me", response_model=list[LeaveOut])
def my_leaves(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Os pedidos do próprio colaborador."""
    return (
        db.query(LeaveRequest)
        .filter(
            LeaveRequest.company_id == current_user.company_id,
            LeaveRequest.collaborator_id == current_user.id,
        )
        .order_by(LeaveRequest.id.desc())
        .all()
    )


@router.get("", response_model=list[LeaveOut])
def list_leaves(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    status: LeaveStatus | None = None,
):
    """
    Directores e Capital Humano veem os pedidos que lhes competem.
    - Director: vê os pendentes de director (e o que já passou).
    - Capital Humano/Administração: vê todos.
    """
    if current_user.role not in (UserRole.DIRECTOR, *CH_ROLES):
        raise HTTPException(status_code=403, detail="Sem acesso.")
    q = db.query(LeaveRequest).filter(LeaveRequest.company_id == current_user.company_id)
    if status:
        q = q.filter(LeaveRequest.status == status)
    return q.order_by(LeaveRequest.id.desc()).all()


# ---------- Aprovação do director ----------

@router.post("/{req_id}/director-approve", response_model=LeaveOut)
def director_approve(
    req_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.DIRECTOR)),
):
    """O director aprova o pedido -> passa a pendente de averbamento pelo CH."""
    req = _get_or_404(db, current_user.company_id, req_id)
    if req.status != LeaveStatus.PENDENTE_DIRECTOR:
        raise HTTPException(status_code=400, detail="O pedido não está pendente do director.")
    req.status = LeaveStatus.PENDENTE_CH
    # Notifica o Capital Humano.
    for ch in db.query(User).filter(
        User.company_id == current_user.company_id, User.role == UserRole.CAPITAL_HUMANO
    ).all():
        notify(
            db, company_id=current_user.company_id, user_id=ch.id,
            title="Ausência para averbar",
            message="Um pedido de ausência foi aprovado pela chefia e aguarda averbamento.",
            category="ausencia", link="/ausencias",
        )
    db.commit()
    db.refresh(req)
    return req


@router.post("/{req_id}/director-reject", response_model=LeaveOut)
def director_reject(
    req_id: int,
    payload: LeaveDecision,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.DIRECTOR)),
):
    """O director recusa o pedido."""
    req = _get_or_404(db, current_user.company_id, req_id)
    if req.status != LeaveStatus.PENDENTE_DIRECTOR:
        raise HTTPException(status_code=400, detail="O pedido não está pendente do director.")
    req.status = LeaveStatus.RECUSADA
    req.decision_note = payload.note
    notify(
        db, company_id=current_user.company_id, user_id=req.collaborator_id,
        title="Pedido de ausência recusado",
        message="A chefia recusou o seu pedido de ausência.",
        category="ausencia", link="/portal",
    )
    db.commit()
    db.refresh(req)
    return req


# ---------- Averbamento do Capital Humano ----------

@router.post("/{req_id}/ch-approve", response_model=LeaveOut)
def ch_approve(
    req_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*CH_ROLES)),
):
    """O Capital Humano averba o pedido -> aprovada."""
    req = _get_or_404(db, current_user.company_id, req_id)
    if req.status != LeaveStatus.PENDENTE_CH:
        raise HTTPException(status_code=400, detail="O pedido não está pendente de averbamento.")
    req.status = LeaveStatus.APROVADA
    # Licença de maternidade: regista no percurso (ajuste do ciclo fica visível).
    if req.leave_type == LeaveType.MATERNIDADE:
        from app.models.career import CareerEvent
        from app.models.enums import CareerEventType
        ev = CareerEvent(
            company_id=req.company_id,
            collaborator_id=req.collaborator_id,
            event_type=CareerEventType.OUTRO,
            event_date=req.start_date,
            title="Licença de maternidade",
            description=(
                f"Licença de maternidade de {req.start_date.isoformat()} a "
                f"{req.end_date.isoformat()} ({req.days} dias). "
                "O ciclo de avaliação neste período é ajustado."
            ),
        )
        db.add(ev)
    notify(
        db, company_id=current_user.company_id, user_id=req.collaborator_id,
        title="Ausência aprovada",
        message="O seu pedido de ausência foi aprovado e averbado.",
        category="ausencia", link="/portal",
    )
    db.commit()
    db.refresh(req)
    return req


@router.post("/{req_id}/ch-reject", response_model=LeaveOut)
def ch_reject(
    req_id: int,
    payload: LeaveDecision,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*CH_ROLES)),
):
    """O Capital Humano recusa no averbamento."""
    req = _get_or_404(db, current_user.company_id, req_id)
    if req.status != LeaveStatus.PENDENTE_CH:
        raise HTTPException(status_code=400, detail="O pedido não está pendente de averbamento.")
    req.status = LeaveStatus.RECUSADA
    req.decision_note = payload.note
    notify(
        db, company_id=current_user.company_id, user_id=req.collaborator_id,
        title="Pedido de ausência recusado",
        message="O Capital Humano recusou o seu pedido de ausência.",
        category="ausencia", link="/portal",
    )
    db.commit()
    db.refresh(req)
    return req


# ---------- Saldo de férias ----------

@router.get("/me/balance", response_model=BalanceOut)
def my_balance(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    year: int | None = None,
):
    """Saldo de férias do ano (22 dias menos os dias de férias já aprovados)."""
    ano = year or date.today().year
    aprovadas = (
        db.query(LeaveRequest)
        .filter(
            LeaveRequest.company_id == current_user.company_id,
            LeaveRequest.collaborator_id == current_user.id,
            LeaveRequest.leave_type == LeaveType.FERIAS,
            LeaveRequest.status == LeaveStatus.APROVADA,
        )
        .all()
    )
    usados = sum(r.days for r in aprovadas if r.start_date.year == ano)
    return BalanceOut(
        year=ano, allowance=ANNUAL_ALLOWANCE, used=usados,
        remaining=ANNUAL_ALLOWANCE - usados,
    )
