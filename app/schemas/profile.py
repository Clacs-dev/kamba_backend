"""
Schemas Pydantic — ficha detalhada do colaborador (secção 2.1).
"""
from datetime import date, datetime
from pydantic import BaseModel, Field

from app.models.enums import ContractType


class ProfileUpdate(BaseModel):
    employee_number: str | None = Field(default=None, max_length=50)
    admission_date: date | None = None
    contract_type: ContractType | None = None
    job_category: str | None = Field(default=None, max_length=150)
    department: str | None = Field(default=None, max_length=150)
    workplace: str | None = Field(default=None, max_length=150)


class ProfileOut(BaseModel):
    user_id: int
    company_id: int
    employee_number: str | None
    admission_date: date | None
    contract_type: ContractType | None
    job_category: str | None
    department: str | None
    workplace: str | None
    updated_at: datetime

    model_config = {"from_attributes": True}