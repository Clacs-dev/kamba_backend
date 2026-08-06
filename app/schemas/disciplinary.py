"""
Schemas Pydantic — processo disciplinar (secção 4).
"""
from datetime import datetime, date
from pydantic import BaseModel, Field

from app.models.enums import DisciplinaryPhase, DisciplinaryOutcome


class ProcessCreate(BaseModel):
    accused_id: int
    reference: str = Field(..., min_length=1, max_length=100)
    imputed_facts: str = Field(..., min_length=3)
    disciplinary_record: str | None = None


class ChargeNoteRequest(BaseModel):
    charge_note: str = Field(..., min_length=3)
    preventive_suspension: bool = False


class DefenseRequest(BaseModel):
    defense_text: str = Field(..., min_length=1)


class DecisionRequest(BaseModel):
    decision_text: str = Field(..., min_length=3)
    outcome: DisciplinaryOutcome


class ProcessOut(BaseModel):
    id: int
    company_id: int
    accused_id: int
    instructor_id: int
    reference: str
    phase: DisciplinaryPhase
    imputed_facts: str
    disciplinary_record: str | None
    charge_note: str | None
    preventive_suspension: bool
    charge_ack_at: datetime | None
    defense_text: str | None
    defense_deadline: date | None
    defense_submitted_at: datetime | None
    decision_text: str | None
    outcome: DisciplinaryOutcome
    decision_ack_at: datetime | None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}