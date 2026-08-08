"""
Schemas Pydantic — Relatórios consolidados da avaliação (secção 3.3).
"""
from pydantic import BaseModel


class GroupStats(BaseModel):
    """Estatísticas de um grupo (uma direção ou uma categoria)."""
    group: str                      # nome da direção ou da categoria
    count: int                      # nº de avaliações validadas no grupo
    average_score: float | None     # média das pontuações
    by_classification: dict[str, int]
    below_threshold: int            # quantos < 3,5


class ConsolidatedReport(BaseModel):
    """
    Relatório consolidado de um ciclo. Contém as três vistas que o manual pede:
    por direção, por categoria, e o geral do ciclo.
    """
    cycle_id: int
    cycle_name: str
    total_validated: int
    overall_average: float | None
    overall_by_classification: dict[str, int]
    by_department: list[GroupStats]
    by_category: list[GroupStats]
