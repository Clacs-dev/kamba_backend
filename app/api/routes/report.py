"""
Rotas dos Relatórios consolidados da avaliação (secção 3.3).

Concluída a validação pela Administração, estes relatórios agregam as
avaliações VALIDADAS de um ciclo em três vistas:
  - geral do ciclo
  - por direção (department da ficha do colaborador)
  - por categoria profissional (technico / dirigente)

Reservado a Administração e Capital Humano.
Isolamento por company_id.
"""
from collections import defaultdict
from pydantic import BaseModel

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
    """Calcula média, distribuição por classificação e nº abaixo do limiar."""
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

    # Todas as avaliações validadas do ciclo.
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

    # --- Geral ---
    all_scores = [e.final_score for e in evals]
    all_class = [e.classification for e in evals]
    overall_avg, overall_by_class, _ = _stats_from(all_scores, all_class)

    # --- Por categoria ---
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

    # --- Por direção (department da ficha) ---
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
    Gera e devolve o relatório consolidado do ciclo em PDF, para arquivo e
    apresentação à Administração / Assembleia Geral (secção 3.3).
    """
    # Reutiliza a mesma lógica de consolidação da rota de dados.
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


# ---------- Cruzamento cultura × desempenho por direção (secção 6) ----------

from app.models.evaluation import EvaluationCycle as _Cycle


class CultureVsPerformanceRow(BaseModel):
    department: str
    performance_average: float | None
    below_threshold: int
    headcount: int


class CultureVsPerformanceOut(BaseModel):
    cycle_id: int
    cycle_name: str
    company_enps: str | None
    company_participation: str | None
    rows: list["CultureVsPerformanceRow"]


@router.get("/culture-vs-performance/{cycle_id}", response_model=CultureVsPerformanceOut)
def culture_vs_performance(
    cycle_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    """
    Cruza o desempenho por direção (médias das avaliações validadas) com os
    indicadores de cultura da empresa — leitura de governação (secção 6):
    onde é que o clima pode estar a travar os resultados.
    """
    cycle = (
        db.query(_Cycle)
        .filter(_Cycle.id == cycle_id, _Cycle.company_id == current_user.company_id)
        .first()
    )
    if not cycle:
        raise HTTPException(status_code=404, detail="Ciclo não encontrado.")

    evals = (
        db.query(Evaluation)
        .filter(
            Evaluation.company_id == current_user.company_id,
            Evaluation.cycle_id == cycle_id,
            Evaluation.phase == EvaluationPhase.VALIDADA,
        )
        .all()
    )

    # Agrupa desempenho por direção.
    por_dir: dict[str, list[float]] = defaultdict(list)
    for e in evals:
        prof = (
            db.query(EmployeeProfile)
            .filter(EmployeeProfile.user_id == e.collaborator_id)
            .first()
        )
        dep = (prof.department if prof and prof.department else "Sem direção")
        if e.final_score is not None:
            por_dir[dep].append(e.final_score)

    rows = []
    for dep, scores in sorted(por_dir.items()):
        avg = round(sum(scores) / len(scores), 2) if scores else None
        below = sum(1 for s in scores if s < SCORE_THRESHOLD)
        rows.append(CultureVsPerformanceRow(
            department=dep, performance_average=avg,
            below_threshold=below, headcount=len(scores),
        ))

    # Indicadores de cultura da empresa (do relatório editável, se existir).
    from app.models.culture_report import CultureReport
    cr = (
        db.query(CultureReport)
        .filter(CultureReport.company_id == current_user.company_id)
        .first()
    )

    return CultureVsPerformanceOut(
        cycle_id=cycle.id, cycle_name=cycle.name,
        company_enps=cr.enps if cr else None,
        company_participation=cr.participation if cr else None,
        rows=rows,
    )
