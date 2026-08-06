"""
Schemas Pydantic — Remuneração e Assiduidade (secção 2.8).
"""
from datetime import datetime
from pydantic import BaseModel, Field


class SalaryCreate(BaseModel):
    collaborator_id: int
    year: int = Field(..., ge=1990, le=2100)
    gross_salary: float = Field(..., ge=0)
    salary_grade: str | None = Field(default=None, max_length=100)


class SalaryOut(BaseModel):
    id: int
    company_id: int
    collaborator_id: int
    year: int
    gross_salary: float
    salary_grade: str | None
    created_at: datetime
    model_config = {"from_attributes": True}


class AttendanceCreate(BaseModel):
    collaborator_id: int
    period: str = Field(..., min_length=1, max_length=50)
    present_days: int = Field(default=0, ge=0)
    justified_absences: int = Field(default=0, ge=0)
    unjustified_absences: int = Field(default=0, ge=0)
    vacation_days_taken: int = Field(default=0, ge=0)


class AttendanceOut(BaseModel):
    id: int
    company_id: int
    collaborator_id: int
    period: str
    present_days: int
    justified_absences: int
    unjustified_absences: int
    vacation_days_taken: int
    created_at: datetime
    model_config = {"from_attributes": True}