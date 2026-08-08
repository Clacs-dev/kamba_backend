"""
Rotas da trilha de auditoria (capítulo 7).

Só a Administração acede — é o órgão que o manual indica para a auditoria.
Isolamento por company_id.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.models.enums import UserRole
from app.models.audit import AuditEvent
from app.api.deps import require_roles

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditEventOut(BaseModel):
    id: int
    actor_name: str
    actor_role: str
    action: str
    detail: str | None
    created_at: datetime
    model_config = {"from_attributes": True}


@router.get("", response_model=list[AuditEventOut])
def list_audit(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMINISTRACAO)),
    limit: int = Query(default=100, le=500),
):
    """A Administração consulta a trilha de auditoria da empresa (mais recentes primeiro)."""
    return (
        db.query(AuditEvent)
        .filter(AuditEvent.company_id == current_user.company_id)
        .order_by(AuditEvent.created_at.desc())
        .limit(limit)
        .all()
    )
