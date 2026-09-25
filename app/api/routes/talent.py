"""
Rotas do Comité de Talento — matriz 9-Box e plano de sucessão.

- O desempenho vem das avaliações VALIDADAS do ciclo (já consolidadas).
- O potencial é o juízo do comité (Capital Humano / Administração), guardado
  na TalentMatrix. Sem potencial atribuído, o colaborador aparece na vista
  com potencial vazio (a aguardar o comité).

Isolamento por company_id.
"""
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.models.enums import UserRole, EvaluationPhase, PotentialLevel
from app.models.evaluation import Evaluation, EvaluationCycle
from app.models.talent import TalentMatrix, SuccessionPlan
from app.schemas.talent import (
    MatrixCreate, MatrixUpdate, MatrixOut,
    SuccessionCreate, SuccessionUpdate, SuccessionOut,
    TalentReportOut,
)
from app.api.deps import require_roles
from app.services.audit import audit

router = APIRouter(prefix="/talent", tags=["talent"])

MANAGE_ROLES = (UserRole.CAPITAL_HUMANO, UserRole.ADMINISTRACAO, UserRole.ADMIN)

SCORE_ALTO = 4.0
SCORE_MEDIO = 3.0
ORDEM_POT = ("alto", "medio", "baixo")
ORDEM_PERC = ("alto", "medio", "baixo")


def _nivel_performance(score: float | None) -> str | None:
    if score is None:
        return None
    if score >= SCORE_ALTO:
        return "alto"
    if score >= SCORE_MEDIO:
        return "medio"
    return "baixo"


def _nome(db: Session, user_id: int | None) -> str | None:
    u = db.query(User).filter(User.id == user_id).first()
    return u.full_name if u else None


def _get_matrix_or_404(db: Session, company_id: int, matrix_id: int) -> TalentMatrix:
    m = (
        db.query(TalentMatrix)
        .filter(TalentMatrix.id == matrix_id, TalentMatrix.company_id == company_id)
        .first()
    )
    if m is None:
        raise HTTPException(status_code=404, detail="Registo de talento não encontrado.")
    return m


def _get_succession_or_404(db: Session, company_id: int, plan_id: int) -> SuccessionPlan:
    p = (
        db.query(SuccessionPlan)
        .filter(SuccessionPlan.id == plan_id, SuccessionPlan.company_id == company_id)
        .first()
    )
    if p is None:
        raise HTTPException(status_code=404, detail="Plano de sucessão não encontrado.")
    return p


# ---------- Matriz (9-Box) ----------


@router.get("/report/{cycle_id}", response_model=TalentReportOut)
def talent_report(
    cycle_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    """Vista consolidada "Talento & Sucessão" do ciclo."""
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

    matrix_map = {
        m.collaborator_id: m
        for m in db.query(TalentMatrix).filter(
            TalentMatrix.company_id == company_id,
            TalentMatrix.cycle_id == cycle_id,
        ).all()
    }

    grid: dict[str, int] = {}
    matrix: list[MatrixOut] = []
    high_potential = 0
    risk_of_exit = 0

    for e in evals:
        m = matrix_map.get(e.collaborator_id)
        score = e.final_score
        perf_level = _nivel_performance(score)
        potential = m.potential if m else None

        if perf_level is not None and potential is not None:
            key = f"{perf_level}_{potential.value}"
            grid[key] = grid.get(key, 0) + 1

        is_hp = perf_level == "alto" and potential == PotentialLevel.ALTO
        risco = bool(m.risk_of_exit) if m else False
        if is_hp:
            high_potential += 1
        if risco:
            risk_of_exit += 1

        matrix.append(MatrixOut(
            id=m.id if m else 0,
            cycle_id=cycle.id,
            cycle_name=cycle.name,
            collaborator_id=e.collaborator_id,
            collaborator_name=_nome(db, e.collaborator_id) or "—",
            position=(m.position if m else None),
            potential=potential,
            performance_score=score,
            performance_level=perf_level,
            is_high_potential=is_hp,
            risk_of_exit=risco,
            notes=(m.notes if m else None),
            updated_at=(m.updated_at if m else e.updated_at),
        ))

    # Ordena: estrelas primeiro, depois por célula, depois por nome.
    def _chave(r: MatrixOut):
        if r.is_high_potential:
            return (0, "")
        if r.performance_level and r.potential:
            return (1, f"{ORDEM_PERC.index(r.performance_level)}_{ORDEM_POT.index(r.potential.value)}")
        return (2, "")
    matrix.sort(key=lambda r: (_chave(r), r.collaborator_name.lower()))

    succession = db.query(SuccessionPlan).filter(
        SuccessionPlan.company_id == company_id
    ).order_by(SuccessionPlan.role_title).all()

    return TalentReportOut(
        cycle_id=cycle.id,
        cycle_name=cycle.name,
        matrix=matrix,
        grid=grid,
        high_potential_count=high_potential,
        risk_of_exit_count=risk_of_exit,
        succession=[_succ_out(db, s) for s in succession],
    )


@router.post("/matrix", response_model=MatrixOut, status_code=status.HTTP_201_CREATED)
def upsert_matrix(
    payload: MatrixCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    company_id = current_user.company_id
    cycle = (
        db.query(EvaluationCycle)
        .filter(EvaluationCycle.id == payload.cycle_id, EvaluationCycle.company_id == company_id)
        .first()
    )
    if cycle is None:
        raise HTTPException(status_code=404, detail="Ciclo não encontrado.")
    collab = (
        db.query(User)
        .filter(User.id == payload.collaborator_id, User.company_id == company_id)
        .first()
    )
    if collab is None:
        raise HTTPException(status_code=404, detail="Colaborador não encontrado nesta empresa.")

    existing = (
        db.query(TalentMatrix)
        .filter(
            TalentMatrix.company_id == company_id,
            TalentMatrix.cycle_id == payload.cycle_id,
            TalentMatrix.collaborator_id == payload.collaborator_id,
        )
        .first()
    )
    if existing:
        existing.potential = payload.potential
        existing.position = payload.position
        existing.risk_of_exit = payload.risk_of_exit
        existing.notes = payload.notes
        m = existing
        db.commit()
        audit(db, actor=current_user, action="talento.potencial_atualizado",
              detail=f"Potencial {payload.potential.value} — {collab.full_name} (ciclo {cycle.name}).")
    else:
        m = TalentMatrix(
            company_id=company_id,
            cycle_id=payload.cycle_id,
            collaborator_id=payload.collaborator_id,
            potential=payload.potential,
            position=payload.position,
            risk_of_exit=payload.risk_of_exit,
            notes=payload.notes,
            created_by=current_user.id,
        )
        db.add(m)
        db.commit()
        audit(db, actor=current_user, action="talento.potencial_atribuido",
              detail=f"Potencial {payload.potential.value} atribuído a {collab.full_name} (ciclo {cycle.name}).")

    db.refresh(m)
    return _matrix_out(db, m, cycle.name)


@router.put("/matrix/{matrix_id}", response_model=MatrixOut)
def update_matrix(
    matrix_id: int,
    payload: MatrixUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    m = _get_matrix_or_404(db, current_user.company_id, matrix_id)
    m.potential = payload.potential
    m.position = payload.position
    m.risk_of_exit = payload.risk_of_exit
    m.notes = payload.notes
    db.commit()
    audit(db, actor=current_user, action="talento.potencial_atualizado",
          detail=f"Registo de talento {matrix_id} atualizado (potencial {payload.potential.value}).")
    db.refresh(m)
    cycle = db.query(EvaluationCycle).filter(EvaluationCycle.id == m.cycle_id).first()
    return _matrix_out(db, m, cycle.name if cycle else "")


@router.delete("/matrix/{matrix_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_matrix(
    matrix_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    m = _get_matrix_or_404(db, current_user.company_id, matrix_id)
    db.delete(m)
    db.commit()
    audit(db, actor=current_user, action="talento.potencial_removido",
          detail=f"Registo de talento {matrix_id} removido.")


# ---------- Plano de sucessão ----------


def _succ_out(db: Session, p: SuccessionPlan) -> SuccessionOut:
    return SuccessionOut(
        id=p.id,
        role_title=p.role_title,
        incumbent_id=p.incumbent_id,
        incumbent_name=_nome(db, p.incumbent_id),
        successor_id=p.successor_id,
        successor_name=_nome(db, p.successor_id) or "—",
        readiness=p.readiness,
        risk_of_exit=p.risk_of_exit,
        notes=p.notes,
        updated_at=p.updated_at,
    )


def _matrix_out(db: Session, m: TalentMatrix, cycle_name: str) -> MatrixOut:
    score = None
    perf_level = None
    e = (
        db.query(Evaluation)
        .filter(
            Evaluation.cycle_id == m.cycle_id,
            Evaluation.collaborator_id == m.collaborator_id,
            Evaluation.phase == EvaluationPhase.VALIDADA,
        )
        .first()
    )
    if e:
        score = e.final_score
        perf_level = _nivel_performance(score)
    return MatrixOut(
        id=m.id,
        cycle_id=m.cycle_id,
        cycle_name=cycle_name,
        collaborator_id=m.collaborator_id,
        collaborator_name=_nome(db, m.collaborator_id) or "—",
        position=m.position,
        potential=m.potential,
        performance_score=score,
        performance_level=perf_level,
        is_high_potential=(perf_level == "alto" and m.potential == PotentialLevel.ALTO),
        risk_of_exit=m.risk_of_exit,
        notes=m.notes,
        updated_at=m.updated_at,
    )


@router.post("/succession", response_model=SuccessionOut, status_code=status.HTTP_201_CREATED)
def create_succession(
    payload: SuccessionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    company_id = current_user.company_id

    successor = (
        db.query(User)
        .filter(User.id == payload.successor_id, User.company_id == company_id)
        .first()
    )
    if successor is None:
        raise HTTPException(status_code=404, detail="Sucessor não encontrado nesta empresa.")

    if payload.incumbent_id is not None:
        incumbent = (
            db.query(User)
            .filter(User.id == payload.incumbent_id, User.company_id == company_id)
            .first()
        )
        if incumbent is None:
            raise HTTPException(status_code=404, detail="Titular não encontrado nesta empresa.")

    p = SuccessionPlan(
        company_id=company_id,
        role_title=payload.role_title,
        incumbent_id=payload.incumbent_id,
        successor_id=payload.successor_id,
        readiness=payload.readiness,
        risk_of_exit=payload.risk_of_exit,
        notes=payload.notes,
        created_by=current_user.id,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    audit(db, actor=current_user, action="talento.sucessao_criada",
          detail=f"Cargo-chave '{p.role_title}' → {successor.full_name}.")
    return _succ_out(db, p)


@router.put("/succession/{plan_id}", response_model=SuccessionOut)
def update_succession(
    plan_id: int,
    payload: SuccessionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    p = _get_succession_or_404(db, current_user.company_id, plan_id)
    p.role_title = payload.role_title
    p.incumbent_id = payload.incumbent_id
    p.successor_id = payload.successor_id
    p.readiness = payload.readiness
    p.risk_of_exit = payload.risk_of_exit
    p.notes = payload.notes
    db.commit()
    db.refresh(p)
    audit(db, actor=current_user, action="talento.sucessao_atualizada",
          detail=f"Plano de sucessão {plan_id} atualizado.")
    return _succ_out(db, p)


@router.delete("/succession/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_succession(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    p = _get_succession_or_404(db, current_user.company_id, plan_id)
    db.delete(p)
    db.commit()
    audit(db, actor=current_user, action="talento.sucessao_removida",
          detail=f"Plano de sucessão {plan_id} removido.")


# ---------- PDF ----------

from app.models.company import Company
from app.services.report_pdf import gerar_pdf_talento


@router.get("/report/{cycle_id}/pdf")
def talent_report_pdf(
    cycle_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    """Gera o PDF da secção Talento & Sucessão do ciclo."""
    report = talent_report(cycle_id, db, current_user)
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    company_name = company.name if company else "Empresa"
    pdf_bytes = gerar_pdf_talento(report, company_name)
    filename = f"talento_sucessao_{report.cycle_name}.pdf".replace(" ", "_")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )