"""
Rotas do ciclo de avaliação (secção 3) — a máquina de seis fases.

Fluxo (3.1):
  1. AUTOAVALIACAO      -> colaborador preenche e submete
  2. AVALIACAO_DIRECTOR -> director avalia e submete (calcula pontuação)
  3. CONCORDANCIA       -> colaborador aceita (->FECHADA) ou recorre (->COMISSAO)
  4. COMISSAO           -> comissão decide (->FECHADA)
  5. FECHADA            -> consolidada
  6. VALIDADA           -> administração valida

Cada transição exige a fase correta E o perfil correto. A plataforma não
deixa saltar fases. Tudo isolado por company_id.
"""
import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.models.enums import UserRole, EvaluationPhase
from app.models.evaluation import EvaluationCycle, Evaluation
from app.schemas.evaluation import (
    CycleCreate, CycleOut, EvaluationCreate, EvaluationOut,
    FormAnswers, AppealRequest, CommissionDecisionRequest,
)
from app.api.deps import get_current_user, require_roles
from app.services.evaluation_scoring import compute_score
from app.services.notifications import notify
from app.services.audit import audit
from datetime import datetime, timezone, timedelta

router = APIRouter(prefix="/evaluations", tags=["evaluations"])


def _add_business_days(start: datetime, days: int) -> datetime:
    """Soma 'days' dias úteis (seg-sex) a uma data, ignorando fins de semana."""
    d = start
    added = 0
    while added < days:
        d = d + timedelta(days=1)
        if d.weekday() < 5:  # 0-4 = segunda a sexta
            added += 1
    return d

MANAGE_ROLES = (UserRole.CAPITAL_HUMANO, UserRole.ADMINISTRACAO)


def _get_eval_or_404(db: Session, company_id: int, evaluation_id: int) -> Evaluation:
    ev = (
        db.query(Evaluation)
        .filter(Evaluation.id == evaluation_id, Evaluation.company_id == company_id)
        .first()
    )
    if ev is None:
        raise HTTPException(status_code=404, detail="Avaliação não encontrada.")
    return ev


def _require_phase(ev: Evaluation, expected: EvaluationPhase):
    if ev.phase != expected:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ação inválida nesta fase. A avaliação está em '{ev.phase.value}', esperava-se '{expected.value}'.",
        )


# ---------- Ciclos (CH gere) ----------

@router.post("/cycles", response_model=CycleOut, status_code=status.HTTP_201_CREATED)
def create_cycle(
    payload: CycleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    cycle = EvaluationCycle(company_id=current_user.company_id, name=payload.name)
    db.add(cycle)
    db.commit()
    db.refresh(cycle)
    return cycle


@router.get("/cycles", response_model=list[CycleOut])
def list_cycles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(EvaluationCycle)
        .filter(EvaluationCycle.company_id == current_user.company_id)
        .order_by(EvaluationCycle.created_at.desc())
        .all()
    )


# ---------- Criar avaliação (CH) ----------

@router.post("", response_model=EvaluationOut, status_code=status.HTTP_201_CREATED)
def create_evaluation(
    payload: EvaluationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    company_id = current_user.company_id

    # Validar que ciclo, colaborador e director pertencem à empresa.
    cycle = (
        db.query(EvaluationCycle)
        .filter(EvaluationCycle.id == payload.cycle_id, EvaluationCycle.company_id == company_id)
        .first()
    )
    if cycle is None:
        raise HTTPException(status_code=404, detail="Ciclo não encontrado.")

    for uid, label in [(payload.collaborator_id, "Colaborador"), (payload.director_id, "Director")]:
        u = db.query(User).filter(User.id == uid, User.company_id == company_id).first()
        if u is None:
            raise HTTPException(status_code=404, detail=f"{label} não encontrado nesta empresa.")

    # Se o colaborador tem licença de maternidade aprovada, o ciclo é ajustado.
    from app.models.leave import LeaveRequest
    from app.models.enums import LeaveType, LeaveStatus
    tem_maternidade = (
        db.query(LeaveRequest)
        .filter(
            LeaveRequest.company_id == company_id,
            LeaveRequest.collaborator_id == payload.collaborator_id,
            LeaveRequest.leave_type == LeaveType.MATERNIDADE,
            LeaveRequest.status == LeaveStatus.APROVADA,
        )
        .first()
        is not None
    )
    ev = Evaluation(
        company_id=company_id,
        cycle_id=payload.cycle_id,
        collaborator_id=payload.collaborator_id,
        director_id=payload.director_id,
        category=payload.category,
        phase=EvaluationPhase.AUTOAVALIACAO,
        cycle_adjusted=tem_maternidade,
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    # Notifica o colaborador de que tem uma autoavaliação pendente.
    notify(
        db, company_id=ev.company_id, user_id=ev.collaborator_id,
        title="Autoavaliação disponível",
        message="Foi iniciada a sua avaliação de desempenho. Preencha a sua autoavaliação.",
        category="avaliacao", link=f"/evaluations/{ev.id}",
    )
    db.commit()
    return ev


@router.get("", response_model=list[EvaluationOut])
def list_evaluations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    cycle_id: int | None = None,
):
    """
    Lista as avaliações relevantes para o utilizador, conforme o perfil:
    - Capital Humano e Administração veem todas as da empresa.
    - Comissão vê todas (para decidir recursos).
    - Director vê as avaliações em que é o avaliador.
    - Colaborador vê apenas as suas.
    Opcionalmente filtra por cycle_id.
    """
    query = db.query(Evaluation).filter(Evaluation.company_id == current_user.company_id)

    if cycle_id is not None:
        query = query.filter(Evaluation.cycle_id == cycle_id)

    role = current_user.role
    if role in (UserRole.CAPITAL_HUMANO, UserRole.ADMINISTRACAO, UserRole.COMISSAO_AVALIACAO):
        pass  # veem todas
    elif role == UserRole.DIRECTOR:
        query = query.filter(Evaluation.director_id == current_user.id)
    else:
        query = query.filter(Evaluation.collaborator_id == current_user.id)

    return query.order_by(Evaluation.id.desc()).all()


@router.get("/{evaluation_id}", response_model=EvaluationOut)
def get_evaluation(
    evaluation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _get_eval_or_404(db, current_user.company_id, evaluation_id)


# ---------- Fase 1: Autoavaliação (colaborador) ----------

@router.post("/{evaluation_id}/self-assessment", response_model=EvaluationOut)
def submit_self_assessment(
    evaluation_id: int,
    answers: FormAnswers,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ev = _get_eval_or_404(db, current_user.company_id, evaluation_id)
    _require_phase(ev, EvaluationPhase.AUTOAVALIACAO)
    if ev.collaborator_id != current_user.id:
        raise HTTPException(status_code=403, detail="Só o próprio colaborador pode submeter a autoavaliação.")

    ev.self_answers = answers.model_dump_json()
    ev.phase = EvaluationPhase.AVALIACAO_DIRECTOR  # -> notifica Director (fase 2)
    notify(
        db, company_id=ev.company_id, user_id=ev.director_id,
        title="Autoavaliação submetida",
        message="Um colaborador submeteu a autoavaliação. Já pode avaliar.",
        category="avaliacao", link=f"/evaluations/{ev.id}",
    )
    db.commit()
    db.refresh(ev)
    return ev


# ---------- Fase 2: Avaliação do Director ----------

@router.post("/{evaluation_id}/director-assessment", response_model=EvaluationOut)
def submit_director_assessment(
    evaluation_id: int,
    answers: FormAnswers,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ev = _get_eval_or_404(db, current_user.company_id, evaluation_id)
    _require_phase(ev, EvaluationPhase.AVALIACAO_DIRECTOR)
    if ev.director_id != current_user.id:
        raise HTTPException(status_code=403, detail="Só o director designado pode avaliar.")

    # Calcula a pontuação a partir das respostas do director,
    # usando as ponderações configuradas pela empresa (secção 8).
    data = answers.model_dump()
    from app.api.routes.evaluation_settings import get_or_create_settings
    from app.models.enums import EvaluationCategory
    cfg = get_or_create_settings(db, current_user.company_id)
    if ev.category == EvaluationCategory.DIRIGENTE:
        pesos = {"objectives": cfg.dir_objectives, "competencies": cfg.dir_competencies, "values": cfg.dir_values}
    else:
        pesos = {"objectives": cfg.tec_objectives, "competencies": cfg.tec_competencies, "values": cfg.tec_values}
    score, classification = compute_score(data, ev.category, weights=pesos)

    ev.director_answers = answers.model_dump_json()
    ev.final_score = score
    ev.classification = classification
    ev.phase = EvaluationPhase.CONCORDANCIA  # -> notifica colaborador (fase 3)
    notify(
        db, company_id=ev.company_id, user_id=ev.collaborator_id,
        title="Avaliação disponível",
        message="A sua chefia concluiu a avaliação. Pode aceitar ou recorrer.",
        category="avaliacao", link=f"/evaluations/{ev.id}",
    )
    db.commit()
    db.refresh(ev)
    return ev


# ---------- Fase 3: Concordância (colaborador aceita ou recorre) ----------

@router.post("/{evaluation_id}/accept", response_model=EvaluationOut)
def accept_evaluation(
    evaluation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ev = _get_eval_or_404(db, current_user.company_id, evaluation_id)
    _require_phase(ev, EvaluationPhase.CONCORDANCIA)
    if ev.collaborator_id != current_user.id:
        raise HTTPException(status_code=403, detail="Só o próprio colaborador pode aceitar.")

    ev.phase = EvaluationPhase.FECHADA  # aceite -> consolidada (fase 5)
    db.commit()
    db.refresh(ev)
    return ev


@router.post("/{evaluation_id}/appeal", response_model=EvaluationOut)
def appeal_evaluation(
    evaluation_id: int,
    payload: AppealRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ev = _get_eval_or_404(db, current_user.company_id, evaluation_id)
    _require_phase(ev, EvaluationPhase.CONCORDANCIA)
    if ev.collaborator_id != current_user.id:
        raise HTTPException(status_code=403, detail="Só o próprio colaborador pode recorrer.")

    ev.appeal_reason = payload.reason
    ev.phase = EvaluationPhase.COMISSAO  # recurso -> comissão (fase 4)
    from app.api.routes.evaluation_settings import get_or_create_settings
    cfg = get_or_create_settings(db, current_user.company_id)
    ev.appeal_deadline = _add_business_days(datetime.now(timezone.utc), cfg.appeal_deadline_days)  # prazo configurável (secção 8)
    # Notifica todos os membros da Comissão de Avaliação da empresa.
    membros = (
        db.query(User)
        .filter(User.company_id == ev.company_id, User.role == UserRole.COMISSAO_AVALIACAO)
        .all()
    )
    for m in membros:
        notify(
            db, company_id=ev.company_id, user_id=m.id,
            title="Novo recurso de avaliação",
            message="Um colaborador recorreu de uma avaliação. A comissão tem 8 dias úteis para decidir.",
            category="avaliacao", link=f"/evaluations/{ev.id}",
        )
    db.commit()
    db.refresh(ev)
    return ev


# ---------- Fase 4: Comissão decide o recurso ----------

@router.post("/{evaluation_id}/commission-decision", response_model=EvaluationOut)
def commission_decision(
    evaluation_id: int,
    payload: CommissionDecisionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.COMISSAO_AVALIACAO)),
):
    ev = _get_eval_or_404(db, current_user.company_id, evaluation_id)
    _require_phase(ev, EvaluationPhase.COMISSAO)

    ev.commission_decision = payload.decision
    ev.phase = EvaluationPhase.FECHADA  # decidido -> consolidada (fase 5)
    # O manual: a decisão é notificada ao colaborador E ao director.
    for uid in (ev.collaborator_id, ev.director_id):
        notify(
            db, company_id=ev.company_id, user_id=uid,
            title="Decisão do recurso",
            message="A Comissão de Avaliação decidiu o recurso. A avaliação está consolidada.",
            category="avaliacao", link=f"/evaluations/{ev.id}",
        )
    db.commit()
    db.refresh(ev)
    return ev


# ---------- Fase 6: Administração valida ----------

@router.post("/{evaluation_id}/validate", response_model=EvaluationOut)
def validate_evaluation(
    evaluation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMINISTRACAO)),
):
    ev = _get_eval_or_404(db, current_user.company_id, evaluation_id)
    _require_phase(ev, EvaluationPhase.FECHADA)

    ev.phase = EvaluationPhase.VALIDADA  # valida -> desencadeia relatório (3.3, futuro)
    audit(db, actor=current_user, action="avaliacao.validada",
          detail=f"Avaliação #{ev.id} validada.")
    db.commit()
    db.refresh(ev)
    return ev


# ---------- Histórico de notas (para o gráfico da Ficha, secção 2.1) ----------

from pydantic import BaseModel as _BaseModel


class ScoreHistoryItem(_BaseModel):
    cycle_id: int
    cycle_name: str
    final_score: float | None
    classification: str | None


@router.get("/me/score-history", response_model=list[ScoreHistoryItem])
def my_score_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = 3,
):
    """
    Histórico das notas validadas do próprio colaborador, dos últimos ciclos
    (por defeito 3), para a evolução gráfica na Ficha.
    """
    rows = (
        db.query(Evaluation, EvaluationCycle)
        .join(EvaluationCycle, Evaluation.cycle_id == EvaluationCycle.id)
        .filter(
            Evaluation.company_id == current_user.company_id,
            Evaluation.collaborator_id == current_user.id,
            Evaluation.phase == EvaluationPhase.VALIDADA,
        )
        .order_by(EvaluationCycle.id.desc())
        .limit(limit)
        .all()
    )
    # Devolve do mais antigo ao mais recente (melhor para gráfico).
    result = [
        ScoreHistoryItem(
            cycle_id=cyc.id, cycle_name=cyc.name,
            final_score=ev.final_score, classification=ev.classification,
        )
        for ev, cyc in rows
    ]
    result.reverse()
    return result


# ---------- Comparação por componente (para o ecrã da comissão) ----------

@router.get("/{evaluation_id}/comparison")
def evaluation_comparison(
    evaluation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Devolve a comparação auto vs director por componente (objetivos,
    competências, valores), com os pesos da empresa. Alimenta o ecrã da
    Comissão de Avaliação e a concordância.
    """
    import json as _json
    from app.services.evaluation_scoring import (
        _score_objectives, _score_competencies, _score_values,
    )
    from app.api.routes.evaluation_settings import get_or_create_settings
    from app.models.enums import EvaluationCategory

    ev = _get_eval_or_404(db, current_user.company_id, evaluation_id)

    cfg = get_or_create_settings(db, current_user.company_id)
    if ev.category == EvaluationCategory.DIRIGENTE:
        pesos = {"objectives": cfg.dir_objectives, "competencies": cfg.dir_competencies, "values": cfg.dir_values}
    else:
        pesos = {"objectives": cfg.tec_objectives, "competencies": cfg.tec_competencies, "values": cfg.tec_values}

    def _scores(raw):
        if not raw:
            return {"objectives": None, "competencies": None, "values": None}
        d = _json.loads(raw)
        return {
            "objectives": round(_score_objectives(d.get("objectives", [])), 2),
            "competencies": round(_score_competencies(d.get("competencies", {})), 2),
            "values": round(_score_values(d.get("values", {})), 2),
        }

    auto = _scores(ev.self_answers)
    director = _scores(ev.director_answers)

    # Nomes das respostas do recorrente/colaborador e do director.
    colab = db.query(User).filter(User.id == ev.collaborator_id).first()
    dirr = db.query(User).filter(User.id == ev.director_id).first()

    return {
        "evaluation_id": ev.id,
        "collaborator_name": colab.full_name if colab else None,
        "director_name": dirr.full_name if dirr else None,
        "weights": {
            "objectives": round(pesos["objectives"] * 100),
            "competencies": round(pesos["competencies"] * 100),
            "values": round(pesos["values"] * 100),
        },
        "auto": auto,
        "director": director,
        "final_score": ev.final_score,
        "appeal_reason": ev.appeal_reason,
        "commission_decision": ev.commission_decision,
        "phase": ev.phase.value if hasattr(ev.phase, "value") else str(ev.phase),
    }
