"""
Cálculo da pontuação da avaliação (secção 3.2 do manual).

O formulário tem três blocos:
- Objetivos: cada um com percentagem de execução (0-100) e um peso próprio.
  A nota do bloco é a média ponderada das execuções, convertida para escala 0-5.
- Competências: cinco indicadores, cada um em escala 1-5. Nota = média.
- Valores: três afirmações Sim/Não. Nota = proporção de "Sim" em escala 0-5.

Ponderação por categoria:
- Técnico:   objetivos 50%, competências 35%, valores 15%
- Dirigente: resultados 60%, liderança 25%, valores 15%
  (mapeados aos mesmos três blocos)

Escala final: <2,5 Insuficiente; 2,5-2,9 Suficiente; 3,0-3,9 Bom;
              4,0-4,4 Muito Bom; >=4,5 Excelente.
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
    """
    objectives: [{"weight": 30, "execution": 80}, ...]
    Média ponderada das execuções (0-100) -> escala 0-5.
    """
    if not objectives:
        return 0.0
    total_weight = sum(o.get("weight", 0) for o in objectives)
    if total_weight <= 0:
        # sem pesos definidos: média simples
        avg_exec = sum(o.get("execution", 0) for o in objectives) / len(objectives)
    else:
        weighted = sum(o.get("execution", 0) * o.get("weight", 0) for o in objectives)
        avg_exec = weighted / total_weight
    return round(avg_exec / 100 * 5, 4)  # 0-100 -> 0-5


def _score_competencies(competencies: dict) -> float:
    """competencies: {"orientacao_resultados": 4, ...} em escala 1-5."""
    vals = [competencies.get(k, 0) for k in COMPETENCY_KEYS]
    if not vals:
        return 0.0
    return round(sum(vals) / len(vals), 4)


def _score_values(values: dict) -> float:
    """values: {"codigo_etica": true, ...} Sim/Não -> proporção em 0-5."""
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


def compute_score(answers: dict, category: EvaluationCategory, weights: dict | None = None) -> tuple[float, str]:
    """
    answers = {
      "objectives": [{"weight":.., "execution":..}, ...],
      "competencies": {chave: 1-5, ...},
      "values": {chave: bool, ...}
    }
    weights (opcional): {"objectives":.., "competencies":.., "values":..} — se
    não for passado, usa as ponderações do manual para a categoria.
    Devolve (pontuacao_final_0a5, classificacao).
    """
    w = weights if weights is not None else WEIGHTS[category]
    s_obj = _score_objectives(answers.get("objectives", []))
    s_comp = _score_competencies(answers.get("competencies", {}))
    s_val = _score_values(answers.get("values", {}))

    final = s_obj * w["objectives"] + s_comp * w["competencies"] + s_val * w["values"]
    final = round(final, 2)
    return final, classify(final)
