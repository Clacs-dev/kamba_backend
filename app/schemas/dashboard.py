"""
Schemas Pydantic — Dashboard (métricas agregadas).
"""
from pydantic import BaseModel


class CollaboratorsMetrics(BaseModel):
    total: int
    active: int
    inactive: int
    by_role: dict[str, int]


class EvaluationMetrics(BaseModel):
    total: int
    in_progress: int
    validated: int
    below_threshold: int
    by_classification: dict[str, int]


class DisciplinaryMetrics(BaseModel):
    total: int
    in_progress: int
    archived: int


class TrainingMetrics(BaseModel):
    plans: int
    actions: int


class HealthMetrics(BaseModel):
    exams: int
    overdue: int


class DashboardSummary(BaseModel):
    collaborators: CollaboratorsMetrics
    evaluations: EvaluationMetrics
    disciplinary: DisciplinaryMetrics
    training: TrainingMetrics
    health: HealthMetrics