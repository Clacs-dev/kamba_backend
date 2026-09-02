"""
Rotas da trilha de auditoria (capítulo 7).

Acesso: Administração e Capital Humano — no protótipo o módulo de
Administração (com a trilha) é visível a CH e CE.
Isolamento por company_id.

Além da listagem, permite EXPORTAR a trilha (CSV ou PDF) para o Conselho de
Administração — suporte probatório de que o procedimento foi cumprido.
"""
import csv
from datetime import datetime
from io import StringIO

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.models.enums import UserRole
from app.models.company import Company
from app.models.audit import AuditEvent
from app.api.deps import require_roles
from app.services.report_pdf import gerar_pdf_auditoria

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditEventOut(BaseModel):
    id: int
    actor_name: str
    actor_role: str
    action: str
    detail: str | None
    created_at: datetime
    model_config = {"from_attributes": True}


def _query_rows(db: Session, company_id: int, limit: int):
    return (
        db.query(AuditEvent)
        .filter(AuditEvent.company_id == company_id)
        .order_by(AuditEvent.created_at.desc())
        .limit(limit)
        .all()
    )


@router.get("", response_model=list[AuditEventOut])
def list_audit(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMINISTRACAO, UserRole.CAPITAL_HUMANO, UserRole.ADMIN)),
    limit: int = Query(default=100, le=500),
):
    """A Administração e o Capital Humano consultam a trilha de auditoria da empresa (mais recentes primeiro)."""
    return _query_rows(db, current_user.company_id, limit)


@router.get("/export")
def export_audit(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMINISTRACAO, UserRole.CAPITAL_HUMANO, UserRole.ADMIN)),
    formato: str = Query(default="csv", pattern="^(csv|pdf)$"),
    limit: int = Query(default=500, le=5000),
):
    """
    Exporta a trilha de auditoria (CSV ou PDF) para o Conselho de Administração.
    Registo imutável, com carimbo temporal — prova documental do procedimento.
    """
    rows = _query_rows(db, current_user.company_id, limit)
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    company_name = company.name if company else "Empresa"

    if formato == "pdf":
        pdf_bytes = gerar_pdf_auditoria(rows, company_name)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="trilha_auditoria.pdf"'},
        )

    # CSV
    buf = StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Data", "Ato", "Autor", "Perfil", "Detalhe"])
    for r in rows:
        ts = r.created_at.strftime("%d/%m/%Y %H:%M") if r.created_at else ""
        writer.writerow([ts, r.action, r.actor_name, r.actor_role, r.detail or ""])
    csv_bytes = buf.getvalue().encode("utf-8-sig")  # BOM para abrir bem no Excel
    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="trilha_auditoria.csv"'},
    )
