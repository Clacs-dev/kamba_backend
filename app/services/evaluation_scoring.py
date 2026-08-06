"""
Cálculo da pontuação da avaliação (secção 3.2 do manual).
"""
from app.models.enums import EvaluationCategory

WEIGHTS = {
    EvaluationCategory.TECNICO: {"objectives": 0.50, "competencies": 0.35, "values": 0.15},
    EvaluationCategory.DIRIGENTE: {"objectives": 0.60, "competencies": 0.25, "values": 0.15},
}

COMPETENCY_KEYS = [
    "orientacao_resultados",
    "trabalho_equipa",
    "etica_conformidade",
    "comunicacao",
    "adaptabilidade",
]

VALUE_KEYS = [
    "codigo_etica",
    "seguranca_saude",
    "assiduidade_pontualidade",
]


def _score_objectives(objectives: list[dict]) -> float:
    if not objectives:
        return 0.0
    total_weight = sum(o.get("weight", 0) for o in objectives)
    if total_weight <= 0:
        avg_exec = sum(o.get("execution", 0) for o in objectives) / len(objectives)
    else:
        weighted = sum(o.get("execution", 0) * o.get("weight", 0) for o in objectives)
        avg_exec = weighted / total_weight
    return round(avg_exec / 100 * 5, 4)


def _score_competencies(competencies: dict) -> float:
    vals = [competencies.get(k, 0) for k in COMPETENCY_KEYS]
    if not vals:
        return 0.0
    return round(sum(vals) / len(vals), 4)


def _score_values(values: dict) -> float:
    vals = [1 if values.get(k) else 0 for k in VALUE_KEYS]
    if not vals:
        return 0.0
    return round(sum(vals) / len(vals) * 5, 4)


def classify(score: float) -> str:
    if score < 2.5:
        return "Insuficiente"
    if score < 3.0:
        return "Suficiente"
    if score < 4.0:
        return "Bom"
    if score < 4.5:
        return "Muito Bom"
    return "Excelente"


def compute_score(answers: dict, category: EvaluationCategory) -> tuple[float, str]:
    w = WEIGHTS[category]
    s_obj = _score_objectives(answers.get("objectives", []))
    s_comp = _score_competencies(answers.get("competencies", {}))
    s_val = _score_values(answers.get("values", {}))

    final = s_obj * w["objectives"] + s_comp * w["competencies"] + s_val * w["values"]
    final = round(final, 2)
    return final, classify(final)