"""
Serviço de auditoria — função única para registar atos.

Os módulos chamam audit(...) nos atos relevantes (validar avaliação, emitir
decisão disciplinar, aprovar plano...). Não faz commit: quem chama já está numa
transação e faz o commit no fim, garantindo que o registo só existe se o ato
também for gravado.
"""
from sqlalchemy.orm import Session

from app.models.audit import AuditEvent
from app.models.user import User


def audit(
    db: Session,
    *,
    actor: User,
    action: str,
    detail: str | None = None,
) -> AuditEvent:
    ev = AuditEvent(
        company_id=actor.company_id,
        actor_id=actor.id,
        actor_name=actor.full_name,
        actor_role=actor.role.value if hasattr(actor.role, "value") else str(actor.role),
        action=action,
        detail=detail,
    )
    db.add(ev)
    return ev
