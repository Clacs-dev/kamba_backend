"""
Schemas Pydantic — ficha detalhada do colaborador (secção 2.1).
"""
from datetime import date, datetime
from pydantic import BaseModel, Field

from app.models.enums import ContractType


class EducationItem(BaseModel):
    """Uma habilitação literária do colaborador (licenciatura, mestrado, ...)."""
    nivel: str | None = None
    ano_inicio: int | None = Field(default=None, ge=1900, le=2200)
    ano_fim: int | None = Field(default=None, ge=1900, le=2200)
    pais: str | None = None


class ExperienceItem(BaseModel):
    """Uma experiência profissional prévia do colaborador."""
    onde: str | None = None
    ano_inicio: int | None = Field(default=None, ge=1900, le=2200)
    ano_fim: int | None = Field(default=None, ge=1900, le=2200)
    funcao: str | None = None


class ProfileUpdate(BaseModel):
    """
    Campos da ficha que o Capital Humano preenche/atualiza.
    Todos opcionais: pode preencher-se aos poucos (atualização parcial).
    """
    employee_number: str | None = Field(default=None, max_length=50)
    admission_date: date | None = None
    contract_type: ContractType | None = None
    job_category: str | None = Field(default=None, max_length=150)
    job_title: str | None = Field(default=None, max_length=150)
    department: str | None = Field(default=None, max_length=150)
    workplace: str | None = Field(default=None, max_length=150)
    work_schedule: str | None = Field(default=None, max_length=200)
    situation_tags: str | None = Field(default=None, max_length=300)
    nationality: str | None = Field(default=None, max_length=100)
    habilitacoes: str | None = Field(default=None, max_length=200)
    university: str | None = Field(default=None, max_length=200)
    course: str | None = Field(default=None, max_length=200)
    cv: str | None = None
    education: list[EducationItem] | None = None
    experience: list[ExperienceItem] | None = None


class ProfileOut(BaseModel):
    """A ficha tal como é devolvida pela API."""
    user_id: int
    company_id: int
    employee_number: str | None
    admission_date: date | None
    contract_type: ContractType | None
    job_category: str | None
    job_title: str | None
    department: str | None
    workplace: str | None
    work_schedule: str | None
    situation_tags: str | None
    nationality: str | None
    habilitacoes: str | None
    university: str | None
    course: str | None
    cv: str | None
    education: list[EducationItem] | None = None
    experience: list[ExperienceItem] | None = None
    photo_url: str | None = None
    policies_signature_pending: bool = False  # calculado: assinaturas em falta
    updated_at: datetime

    model_config = {"from_attributes": True}
