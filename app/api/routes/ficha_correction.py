"""
Rotas do pedido de correção da ficha (secção 2.1).

- Colaborador: submete um pedido e vê os seus pedidos.
- Capital Humano / Administração: veem todos os pedidos e marcam-nos como resolvidos.
Ao submeter, o Capital Humano é notificado.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.models.enums import UserRole
from app.models.ficha_correction import FichaCorrectionRequest
from app.api.deps import get_current_user, require_roles
from app.services.notifications import notify

router = APIRouter(prefix="/ficha-corrections", tags=["ficha-corrections"])

MANAGE = (UserRole.CAPITAL_HUMANO, UserRole.ADMINISTRACAO)


class CorrectionIn(BaseModel):
    message: str = Field(..., min_length=3, max_length=1000)


class CorrectionOut(BaseModel):
    id: int
    collaborator_id: int
    message: str
    status: str
    created_at: datetime
    resolved_at: datetime | None
    model_config = {"from_attributes": True}


@router.post("", response_model=CorrectionOut, status_code=201)
def submit_correction(
    payload: CorrectionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """O colaborador requer uma correção à sua ficha."""
    req = FichaCorrectionRequest(
        company_id=current_user.company_id,
        collaborator_id=current_user.id,
        message=payload.message,
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    # Notifica os gestores de RH da empresa.
    gestores = (
        db.query(User)
        .filter(
            User.company_id == current_user.company_id,
            User.role == UserRole.CAPITAL_HUMANO,
        )
        .all()
    )
    for g in gestores:
        notify(
            db, company_id=current_user.company_id, user_id=g.id,
            title="Pedido de correção de ficha",
            message=f"{current_user.full_name} requereu uma correção à ficha.",
            category="ficha", link="/colaboradores",
        )
    db.commit()
    return req


@router.get("/me", response_model=list[CorrectionOut])
def my_corrections(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """O colaborador vê os seus próprios pedidos."""
    return (
        db.query(FichaCorrectionRequest)
        .filter(
            FichaCorrectionRequest.company_id == current_user.company_id,
            FichaCorrectionRequest.collaborator_id == current_user.id,
        )
        .order_by(FichaCorrectionRequest.id.desc())
        .all()
    )


@router.get("", response_model=list[CorrectionOut])
def list_corrections(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE)),
    status: str | None = None,
):
    """O Capital Humano vê todos os pedidos da empresa (opcionalmente filtra por estado)."""
    q = db.query(FichaCorrectionRequest).filter(
        FichaCorrectionRequest.company_id == current_user.company_id
    )
    if status:
        q = q.filter(FichaCorrectionRequest.status == status)
    return q.order_by(FichaCorrectionRequest.id.desc()).all()


@router.post("/{request_id}/resolve", response_model=CorrectionOut)
def resolve_correction(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE)),
):
    """O Capital Humano marca um pedido como resolvido e avisa o colaborador."""
    req = (
        db.query(FichaCorrectionRequest)
        .filter(
            FichaCorrectionRequest.id == request_id,
            FichaCorrectionRequest.company_id == current_user.company_id,
        )
        .first()
    )
    if not req:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")
    req.status = "resolvido"
    req.resolved_at = datetime.now(timezone.utc)
    notify(
        db, company_id=current_user.company_id, user_id=req.collaborator_id,
        title="Pedido de correção tratado",
        message="O seu pedido de correção da ficha foi tratado pelo Capital Humano.",
        category="ficha", link="/portal",
    )
    db.commit()
    db.refresh(req)
    return req
