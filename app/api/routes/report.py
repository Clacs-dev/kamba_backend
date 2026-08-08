"""
Rotas dos Relatórios consolidados da avaliação (secção 3.3).
Agrega as avaliações validadas de um ciclo: geral, por direção, por categoria.
Reservado a Administração e Capital Humano.
"""
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.models.enums import UserRole, EvaluationPhase
from app.models.evaluation import Evaluation, EvaluationCycle
from app.models.employee_profile import EmployeeProfile
from app.schemas.report import ConsolidatedReport, GroupStats
from app.api.deps import require_roles

router = APIRouter(prefix="/reports", tags=["reports"])

MANAGE_ROLES = (UserRole.CAPITAL_HUMANO, UserRole.ADMINISTRACAO)
SCORE_THRESHOLD = 3.5


def _stats_from(scores: list[float], classifications: list[str]) -> tuple[float | None, dict, int]:
    if not scores:
        return None, {}, 0
    avg = round(sum(scores) / len(scores), 2)
    by_class: dict[str, int] = defaultdict(int)
    for c in classifications:
        if c:
            by_class[c] += 1
    below = sum(1 for s in scores if s < SCORE_THRESHOLD)
    return avg, dict(by_class), below


@router.get("/evaluations/{cycle_id}", response_model=ConsolidatedReport)
def consolidated_report(
    cycle_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    company_id = current_user.company_id

    cycle = (
        db.query(EvaluationCycle)
        .filter(EvaluationCycle.id == cycle_id, EvaluationCycle.company_id == company_id)
        .first()
    )
    if cycle is None:
        raise HTTPException(status_code=404, detail="Ciclo não encontrado.")

    evals = (
        db.query(Evaluation)
        .filter(
            Evaluation.company_id == company_id,
            Evaluation.cycle_id == cycle_id,
            Evaluation.phase == EvaluationPhase.VALIDADA,
            Evaluation.final_score.isnot(None),
        )
        .all()
    )

    all_scores = [e.final_score for e in evals]
    all_class = [e.classification for e in evals]
    overall_avg, overall_by_class, _ = _stats_from(all_scores, all_class)

    cat_scores: dict[str, list[float]] = defaultdict(list)
    cat_class: dict[str, list[str]] = defaultdict(list)
    for e in evals:
        cat_scores[e.category.value].append(e.final_score)
        cat_class[e.category.value].append(e.classification)

    by_category = []
    for cat, scores in cat_scores.items():
        avg, by_class, below = _stats_from(scores, cat_class[cat])
        by_category.append(GroupStats(
            group=cat, count=len(scores), average_score=avg,
            by_classification=by_class, below_threshold=below,
        ))

    dep_scores: dict[str, list[float]] = defaultdict(list)
    dep_class: dict[str, list[str]] = defaultdict(list)
    for e in evals:
        profile = (
            db.query(EmployeeProfile)
            .filter(EmployeeProfile.user_id == e.collaborator_id)
            .first()
        )
        dep = (profile.department if profile and profile.department else "Sem direção")
        dep_scores[dep].append(e.final_score)
        dep_class[dep].append(e.classification)

    by_department = []
    for dep, scores in dep_scores.items():
        avg, by_class, below = _stats_from(scores, dep_class[dep])
        by_department.append(GroupStats(
            group=dep, count=len(scores), average_score=avg,
            by_classification=by_class, below_threshold=below,
        ))

    return ConsolidatedReport(
        cycle_id=cycle.id,
        cycle_name=cycle.name,
        total_validated=len(evals),
        overall_average=overall_avg,
        overall_by_classification=overall_by_class,
        by_department=by_department,
        by_category=by_category,
    )


# ---------- PDF do relatório consolidado ----------

from fastapi import Response
from app.models.company import Company
from app.services.report_pdf import gerar_pdf_relatorio


@router.get("/evaluations/{cycle_id}/pdf")
def consolidated_report_pdf(
    cycle_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    """
    Gera e devolve o relatório consolidado do ciclo em PDF (secção 3.3).
    """
    report = consolidated_report(cycle_id, db, current_user)

    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    company_name = company.name if company else "Empresa"

    pdf_bytes = gerar_pdf_relatorio(report, company_name)

    filename = f"relatorio_{report.cycle_name}.pdf".replace(" ", "_")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )