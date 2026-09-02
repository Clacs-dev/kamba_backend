"""
Rotas da parametrização do ciclo de avaliação (secção 8).

- GET: qualquer utilizador da empresa pode consultar os parâmetros em vigor.
- PUT: só Capital Humano e Administração podem alterar.
As ponderações de cada categoria têm de somar 1.0 (100%).
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.models.enums import UserRole
from app.models.evaluation_settings import EvaluationSettings
from app.api.deps import get_current_user, require_roles
from app.services.audit import audit

router = APIRouter(prefix="/evaluation-settings", tags=["evaluation-settings"])

MANAGE = (UserRole.CAPITAL_HUMANO, UserRole.ADMINISTRACAO, UserRole.ADMIN)


class SettingsOut(BaseModel):
    tec_objectives: float
    tec_competencies: float
    tec_values: float
    dir_objectives: float
    dir_competencies: float
    dir_values: float
    appeal_deadline_days: int
    cycle_calendar: str | None
    model_config = {"from_attributes": True}


class SettingsUpdate(BaseModel):
    tec_objectives: float = Field(..., ge=0, le=1)
    tec_competencies: float = Field(..., ge=0, le=1)
    tec_values: float = Field(..., ge=0, le=1)
    dir_objectives: float = Field(..., ge=0, le=1)
    dir_competencies: float = Field(..., ge=0, le=1)
    dir_values: float = Field(..., ge=0, le=1)
    appeal_deadline_days: int = Field(..., ge=1, le=60)
    cycle_calendar: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _somam_um(self):
        tec = round(self.tec_objectives + self.tec_competencies + self.tec_values, 3)
        dgt = round(self.dir_objectives + self.dir_competencies + self.dir_values, 3)
        if tec != 1.0:
            raise ValueError("As ponderações do técnico têm de somar 100%.")
        if dgt != 1.0:
            raise ValueError("As ponderações do dirigente têm de somar 100%.")
        return self


def get_or_create_settings(db: Session, company_id: int) -> EvaluationSettings:
    """Devolve as definições da empresa, criando-as com os valores do manual se não existirem."""
    s = (
        db.query(EvaluationSettings)
        .filter(EvaluationSettings.company_id == company_id)
        .first()
    )
    if s is None:
        s = EvaluationSettings(company_id=company_id)
        db.add(s)
        db.commit()
        db.refresh(s)
    return s


@router.get("", response_model=SettingsOut)
def get_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_or_create_settings(db, current_user.company_id)


@router.put("", response_model=SettingsOut)
def update_settings(
    payload: SettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE)),
):
    s = get_or_create_settings(db, current_user.company_id)
    s.tec_objectives = payload.tec_objectives
    s.tec_competencies = payload.tec_competencies
    s.tec_values = payload.tec_values
    s.dir_objectives = payload.dir_objectives
    s.dir_competencies = payload.dir_competencies
    s.dir_values = payload.dir_values
    s.appeal_deadline_days = payload.appeal_deadline_days
    s.cycle_calendar = payload.cycle_calendar
    audit(db, actor=current_user, action="avaliacao.parametros_alterados",
          detail=f"Ponderações (técnico {payload.tec_objectives:.0%}/{payload.tec_competencies:.0%}/{payload.tec_values:.0%}, "
                 f"dirigente {payload.dir_objectives:.0%}/{payload.dir_competencies:.0%}/{payload.dir_values:.0%}), "
                 f"prazo de recurso {payload.appeal_deadline_days} dias úteis.")
    db.commit()
    db.refresh(s)
    return s
