"""
Schemas Pydantic — Relatórios consolidados da avaliação (secção 3.3).
"""
from pydantic import BaseModel


class GroupStats(BaseModel):
    group: str
    count: int
    average_score: float | None
    by_classification: dict[str, int]
    below_threshold: int


class ConsolidatedReport(BaseModel):
    cycle_id: int
    cycle_name: str
    total_validated: int
    overall_average: float | None
    overall_by_classification: dict[str, int]
    by_department: list[GroupStats]
    by_category: list[GroupStats]