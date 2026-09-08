"""
Schemas Pydantic — turnos da empresa (alterações 8 e 9).
"""
from datetime import time
from pydantic import BaseModel, Field, model_validator


class ShiftCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    start_time: time
    end_time: time
    break_start: time | None = None
    break_end: time | None = None

    @model_validator(mode="after")
    def _validar_horas(self) -> "ShiftCreate":
        if self.break_start and self.break_end and self.break_end <= self.break_start:
            raise ValueError("O fim do intervalo tem de ser depois do início.")
        return self


class ShiftUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    start_time: time | None = None
    end_time: time | None = None
    break_start: time | None = None
    break_end: time | None = None
    is_active: bool | None = None


class ShiftOut(BaseModel):
    id: int
    company_id: int
    name: str
    start_time: time
    end_time: time
    break_start: time | None
    break_end: time | None
    is_active: bool

    model_config = {"from_attributes": True}
