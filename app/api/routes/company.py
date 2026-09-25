"""
Rota pública autenticada da empresa — identidade (visão, missão, valores,
objetivos) exibida no rodapé de todas as páginas da empresa.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.models.company import Company
from app.api.deps import get_current_user

router = APIRouter(prefix="/company", tags=["company"])


@router.get("/identity")
def company_identity(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Identidade da empresa do utilizador autenticado (qualquer perfil)."""
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    if company is None:
        return {
            "name": "",
            "vision": None, "mission": None, "values": None, "objectives": None,
        }
    return {
        "name": company.name,
        "vision": company.vision,
        "mission": company.mission,
        "values": company.values,
        "objectives": company.objectives,
    }