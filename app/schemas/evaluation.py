"""
Schemas Pydantic — ciclo de avaliação (secção 3).
"""
from datetime import datetime, timezone
from pydantic import BaseModel, Field, computed_field, field_validator

from app.models.enums import EvaluationPhase, EvaluationCategory


# --- Ciclo ---

# Configuração de etapas do formulário de avaliação.
class StageItem(BaseModel):
    """Item dentro de uma etapa (objetivo, competência, valor, etc.)."""
    description: str = Field(..., min_length=1, max_length=300)
    weight: float | None = None          # peso (apenas para objetivos)
    scale: list[str] | None = None       # rótulos da escala (apenas para competências)

class StageConfig(BaseModel):
    """Uma etapa do formulário de avaliação."""
    number: int = Field(..., ge=1, le=10)
    name: str = Field(..., min_length=1, max_length=150)
    weight: float = Field(default=0, ge=0, le=100)
    stage_type: str = Field(..., pattern=r"^(objectives|competencies|values|notes)$")
    items: list[StageItem] = []

class FormConfig(BaseModel):
    """Configuração completa do formulário de avaliação de um ciclo."""
    stages: list[StageConfig] = []

# Defaults do formulário de avaliação.
DEFAULT_FORM_CONFIG: dict = {
    "stages": [
        {
            "number": 1,
            "name": "Objectivos pactuados",
            "weight": 50,
            "stage_type": "objectives",
            "items": [
                {"description": "Atingir 100% da meta anual de vendas da equipa", "weight": 40},
                {"description": "Reduzir o prazo médio de recebimento da carteira para 60 dias", "weight": 30},
                {"description": "Garantir a adopção do CRM por 90% da equipa comercial", "weight": 30},
            ],
        },
        {
            "number": 2,
            "name": "Competências",
            "weight": 35,
            "stage_type": "competencies",
            "items": [
                {"description": "Orientação para resultados", "scale": ["Raramente", "Às vezes", "Com regularidade", "Quase sempre", "Sempre"]},
                {"description": "Trabalho em equipa e colaboração", "scale": ["Raramente", "Às vezes", "Com regularidade", "Quase sempre", "Sempre"]},
                {"description": "Ética e conformidade", "scale": ["Raramente", "Às vezes", "Com regularidade", "Quase sempre", "Sempre"]},
                {"description": "Comunicação", "scale": ["Raramente", "Às vezes", "Com regularidade", "Quase sempre", "Sempre"]},
                {"description": "Adaptabilidade e melhoria contínua", "scale": ["Raramente", "Às vezes", "Com regularidade", "Quase sempre", "Sempre"]},
            ],
        },
        {
            "number": 3,
            "name": "Valores e conduta",
            "weight": 15,
            "stage_type": "values",
            "items": [
                {"description": "Cumpri o Código de Ética e Conduta da empresa"},
                {"description": "Cumpri as normas de segurança e saúde no trabalho"},
                {"description": "Mantive assiduidade e pontualidade regulares"},
            ],
        },
    ]
}


class CycleCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=150)


class CycleOut(BaseModel):
    id: int
    company_id: int
    name: str
    is_open: bool
    form_config: dict | None = None
    created_at: datetime
    model_config = {"from_attributes": True}


# --- Avaliação: criação ---

class DefinedObjective(BaseModel):
    """Objetivo pactuado, definido pelo Capital Humano no início do ciclo."""
    description: str = Field(..., min_length=2, max_length=300)
    weight: float = Field(..., ge=0, le=100)


class EvaluationCreate(BaseModel):
    cycle_id: int
    collaborator_id: int
    director_id: int
    category: EvaluationCategory = EvaluationCategory.TECNICO
    objectives: list[DefinedObjective] = []
    department: str | None = None  # se preenchido, cria para TODA a direção


class DirectionCreate(BaseModel):
    """Cria uma avaliação para TODOS os colaboradores de uma direção."""
    cycle_id: int
    director_id: int
    department: str
    category: EvaluationCategory = EvaluationCategory.TECNICO
    objectives: list[DefinedObjective] = []


# --- Respostas do formulário (blocos do 3.2) ---

class Objective(BaseModel):
    description: str = ""
    weight: float = Field(default=0, ge=0)          # peso do objetivo
    execution: float = Field(default=0, ge=0, le=100)  # % de execução


class FormAnswers(BaseModel):
    objectives: list[Objective] = []
    competencies: dict[str, int] = {}   # chave -> 1..5
    values: dict[str, bool] = {}        # chave -> Sim/Não


# --- Ações de transição ---

class AppealRequest(BaseModel):
    reason: str = Field(..., min_length=3)


class CommissionDecisionRequest(BaseModel):
    decision: str = Field(..., min_length=3)


# --- Saída ---

class EvaluationOut(BaseModel):
    id: int
    company_id: int
    cycle_id: int
    collaborator_id: int
    director_id: int
    category: EvaluationCategory
    phase: EvaluationPhase
    final_score: float | None
    classification: str | None
    appeal_reason: str | None
    appeal_deadline: datetime | None = None
    cycle_adjusted: bool = False
    commission_decision: str | None
    objectives: list[DefinedObjective] = Field(default=[], validation_alias="defined_objectives")
    created_at: datetime
    updated_at: datetime

    @field_validator("objectives", mode="before")
    @classmethod
    def _parse_objectives(cls, v):
        if v is None or v == []:
            return []
        if isinstance(v, str):
            import json as _json
            try:
                return _json.loads(v)
            except Exception:
                return []
        return v

    model_config = {"from_attributes": True, "populate_by_name": True}

    @computed_field
    @property
    def appeal_overdue(self) -> bool:
        """True se há um prazo de recurso e já foi ultrapassado (e ainda em comissão)."""
        if self.appeal_deadline is None:
            return False
        if self.phase != EvaluationPhase.COMISSAO:
            return False
        agora = datetime.now(timezone.utc)
        prazo = self.appeal_deadline
        if prazo.tzinfo is None:
            prazo = prazo.replace(tzinfo=timezone.utc)
        return agora > prazo

    @computed_field
    @property
    def appeal_days_left(self) -> int | None:
        """Dias (corridos) até ao prazo do recurso; negativo se já passou. None se não aplicável."""
        if self.appeal_deadline is None or self.phase != EvaluationPhase.COMISSAO:
            return None
        agora = datetime.now(timezone.utc)
        prazo = self.appeal_deadline
        if prazo.tzinfo is None:
            prazo = prazo.replace(tzinfo=timezone.utc)
        return (prazo - agora).days


class EvaluationListOut(EvaluationOut):
    """Igual à saída de uma avaliação, mas com os nomes das pessoas (para as
    listas e dossiers, sem o frontend ter de pedir a lista de colaboradores)."""
    collaborator_name: str | None = None
    director_name: str | None = None
