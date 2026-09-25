"""
Schemas Pydantic — Comité de Talento (9-Box) e plano de sucessão.
"""
from datetime import datetime
from pydantic import BaseModel, Field

from app.models.enums import PotentialLevel, ReadinessLevel


class MatrixCreate(BaseModel):
    cycle_id: int
    collaborator_id: int
    potential: PotentialLevel
    position: str | None = Field(default=None, max_length=150)
    risk_of_exit: bool = False
    notes: str | None = None


class MatrixUpdate(BaseModel):
    potential: PotentialLevel
    position: str | None = Field(default=None, max_length=150)
    risk_of_exit: bool = False
    notes: str | None = None


class MatrixOut(BaseModel):
    id: int
    cycle_id: int
    cycle_name: str
    collaborator_id: int
    collaborator_name: str
    position: str | None
    potential: PotentialLevel | None
    performance_score: float | None
    performance_level: str | None   # "alto" | "medio" | "baixo" derivado da nota
    is_high_potential: bool         # desempenho alto + potencial alto
    risk_of_exit: bool
    notes: str | None
    updated_at: datetime
    model_config = {"from_attributes": True}


class SuccessionCreate(BaseModel):
    role_title: str = Field(..., min_length=2, max_length=150)
    incumbent_id: int | None = None
    successor_id: int
    readiness: ReadinessLevel = ReadinessLevel.EM_12_MESES
    risk_of_exit: bool = False
    notes: str | None = None


class SuccessionUpdate(BaseModel):
    role_title: str = Field(..., min_length=2, max_length=150)
    incumbent_id: int | None = None
    successor_id: int
    readiness: ReadinessLevel = ReadinessLevel.EM_12_MESES
    risk_of_exit: bool = False
    notes: str | None = None


class SuccessionOut(BaseModel):
    id: int
    role_title: str
    incumbent_id: int | None
    incumbent_name: str | None
    successor_id: int
    successor_name: str
    readiness: ReadinessLevel
    risk_of_exit: bool
    notes: str | None
    updated_at: datetime
    model_config = {"from_attributes": True}


class TalentReportOut(BaseModel):
    """Vista "Talento & Sucessão" de um ciclo para os relatórios."""
    cycle_id: int
    cycle_name: str
    matrix: list[MatrixOut]         # todos os avaliados do ciclo (com ou sem potencial)
    grid: dict[str, int]            # as 9 células: "alto_alto", "alto_medio", ...
    high_potential_count: int       # estrelas (desempenho+potencial altos)
    risk_of_exit_count: int         # risco de saída assinalado pelo comité
    succession: list[SuccessionOut]