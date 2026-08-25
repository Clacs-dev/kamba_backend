"""
Rotas da cultura organizacional (secção 6) — inquéritos-pulso anónimos.

Garantias de anonimato:
1. A resposta é gravada sem user_id (tabela SurveyResponse).
2. A participação é gravada à parte (tabela SurveyParticipation), só para
   impedir dupla resposta. As duas nunca se cruzam.
3. Os resultados só são revelados com >= 5 respostas.

Isolamento por company_id.
"""
import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.models.enums import UserRole, SurveyStatus
from app.models.survey import Survey, SurveyResponse, SurveyParticipation
from app.schemas.survey import (
    SurveyCreate, SurveyOut, SurveyResponseSubmit, SurveyResults,
)
from app.api.deps import get_current_user, require_roles
from app.services.audit import audit

router = APIRouter(prefix="/surveys", tags=["culture"])

# Criação/fecho de pulses: Capital Humano e Administração, mais o Director.
SURVEY_ROLES = (UserRole.CAPITAL_HUMANO, UserRole.ADMINISTRACAO, UserRole.DIRECTOR)
MANAGE_ROLES = (UserRole.CAPITAL_HUMANO, UserRole.ADMINISTRACAO)
MIN_RESPONSES = 5  # limiar de anonimato (secção 6)


def _get_survey_or_404(db: Session, company_id: int, survey_id: int) -> Survey:
    s = (
        db.query(Survey)
        .filter(Survey.id == survey_id, Survey.company_id == company_id)
        .first()
    )
    if s is None:
        raise HTTPException(status_code=404, detail="Inquérito não encontrado.")
    return s


def _to_out(s: Survey) -> SurveyOut:
    return SurveyOut(
        id=s.id, company_id=s.company_id, title=s.title,
        dimensions=json.loads(s.dimensions), status=s.status, created_at=s.created_at,
    )


@router.post("", response_model=SurveyOut, status_code=status.HTTP_201_CREATED)
def create_survey(
    payload: SurveyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*SURVEY_ROLES)),
):
    survey = Survey(
        company_id=current_user.company_id,
        title=payload.title,
        dimensions=json.dumps(payload.dimensions),
    )
    db.add(survey)
    audit(db, actor=current_user, action="cultura.pulse_criado",
          detail=f"Inquérito-pulso '{payload.title}' criado ({len(payload.dimensions)} dimensões).")
    db.commit()
    db.refresh(survey)
    return _to_out(survey)


@router.get("", response_model=list[SurveyOut])
def list_surveys(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    surveys = (
        db.query(Survey)
        .filter(Survey.company_id == current_user.company_id)
        .order_by(Survey.created_at.desc())
        .all()
    )
    return [_to_out(s) for s in surveys]


@router.post("/{survey_id}/respond", status_code=status.HTTP_201_CREATED)
def respond(
    survey_id: int,
    payload: SurveyResponseSubmit,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Submete uma resposta anónima. Regista a participação (para impedir dupla
    resposta) e a resposta (sem ligação ao utilizador), em separado.
    """
    survey = _get_survey_or_404(db, current_user.company_id, survey_id)
    if survey.status != SurveyStatus.ABERTO:
        raise HTTPException(status_code=409, detail="Este inquérito está fechado.")

    # Já participou?
    already = (
        db.query(SurveyParticipation)
        .filter(
            SurveyParticipation.survey_id == survey.id,
            SurveyParticipation.user_id == current_user.id,
        )
        .first()
    )
    if already:
        raise HTTPException(status_code=409, detail="Já respondeu a este inquérito.")

    # Validar dimensões e escala.
    valid_dims = set(json.loads(survey.dimensions))
    for dim, val in payload.answers.items():
        if dim not in valid_dims:
            raise HTTPException(status_code=422, detail=f"Dimensão inválida: {dim}.")
        if not (1 <= val <= 5):
            raise HTTPException(status_code=422, detail="As respostas devem estar entre 1 e 5.")

    # Gravar participação e resposta SEPARADAMENTE.
    db.add(SurveyParticipation(
        company_id=current_user.company_id, survey_id=survey.id, user_id=current_user.id
    ))
    db.add(SurveyResponse(
        company_id=current_user.company_id, survey_id=survey.id,
        answers=json.dumps(payload.answers),
    ))
    db.commit()
    return {"detail": "Resposta registada anonimamente."}


@router.post("/{survey_id}/close", response_model=SurveyOut)
def close_survey(
    survey_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*SURVEY_ROLES)),
):
    survey = _get_survey_or_404(db, current_user.company_id, survey_id)
    survey.status = SurveyStatus.FECHADO
    audit(db, actor=current_user, action="cultura.pulse_fechado",
          detail=f"Inquérito-pulso '{survey.title}' fechado.")
    db.commit()
    db.refresh(survey)
    return _to_out(survey)


@router.get("/{survey_id}/results", response_model=SurveyResults)
def get_results(
    survey_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    """
    Resultados agregados. Só revelados com >= 5 respostas (anonimato).
    Calcula ainda a participação: universo (colaboradores ativos) e taxa.
    """
    survey = _get_survey_or_404(db, current_user.company_id, survey_id)

    responses = (
        db.query(SurveyResponse)
        .filter(SurveyResponse.survey_id == survey.id)
        .all()
    )
    count = len(responses)

    # Participação (secção 6): universo de colaboradores ativos, participações
    # registadas e taxa — calculados, não preenchidos à mão.
    universe = (
        db.query(User)
        .filter(User.company_id == current_user.company_id, User.is_active.is_(True))
        .count()
    )
    participation_count = (
        db.query(SurveyParticipation)
        .filter(SurveyParticipation.survey_id == survey.id)
        .count()
    )
    participation_rate = (
        round(participation_count * 100 / universe, 1) if universe else None
    )

    if count < MIN_RESPONSES:
        return SurveyResults(
            survey_id=survey.id,
            response_count=count,
            released=False,
            results={},
            note=f"Resultados ocultados: são necessárias pelo menos {MIN_RESPONSES} respostas para proteger o anonimato.",
            participation_count=participation_count,
            universe=universe,
            participation_rate=participation_rate,
        )

    # Agregar médias por dimensão.
    dims = json.loads(survey.dimensions)
    totals = {d: 0 for d in dims}
    counts = {d: 0 for d in dims}
    for r in responses:
        ans = json.loads(r.answers)
        for d, v in ans.items():
            if d in totals:
                totals[d] += v
                counts[d] += 1

    results = {
        d: round(totals[d] / counts[d], 2)
        for d in dims if counts[d] > 0
    }
    return SurveyResults(
        survey_id=survey.id,
        response_count=count,
        released=True,
        results=results,
        note="Resultados agregados.",
        participation_count=participation_count,
        universe=universe,
        participation_rate=participation_rate,
    )


# ---------- Relatório de cultura (editado pelo Capital Humano) ----------

import json as _json
from app.models.culture_report import CultureReport
from app.schemas.culture_report import CultureReportIn, CultureReportOut, DimensionRow


def _report_to_out(r: CultureReport | None) -> CultureReportOut:
    if r is None:
        return CultureReportOut()
    dims = []
    if r.dimensions_json:
        try:
            dims = [DimensionRow(**d) for d in _json.loads(r.dimensions_json)]
        except Exception:
            dims = []
    recs = []
    if r.recommendations_json:
        try:
            recs = _json.loads(r.recommendations_json)
        except Exception:
            recs = []
    return CultureReportOut(
        enps=r.enps, participation=r.participation, pulses_note=r.pulses_note,
        dimensions=dims, recommendations=recs,
    )


@router.get("/culture-report/data", response_model=CultureReportOut)
def get_culture_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Qualquer utilizador da empresa consulta o relatório de cultura."""
    r = (
        db.query(CultureReport)
        .filter(CultureReport.company_id == current_user.company_id)
        .first()
    )
    return _report_to_out(r)


@router.put("/culture-report/data", response_model=CultureReportOut)
def put_culture_report(
    payload: CultureReportIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CAPITAL_HUMANO, UserRole.ADMINISTRACAO)),
):
    """O Capital Humano/Administração edita o relatório de cultura da empresa."""
    r = (
        db.query(CultureReport)
        .filter(CultureReport.company_id == current_user.company_id)
        .first()
    )
    if r is None:
        r = CultureReport(company_id=current_user.company_id)
        db.add(r)

    r.enps = payload.enps
    r.participation = payload.participation
    r.pulses_note = payload.pulses_note
    r.dimensions_json = _json.dumps([d.model_dump() for d in payload.dimensions])
    r.recommendations_json = _json.dumps(payload.recommendations)

    db.commit()
    db.refresh(r)
    return _report_to_out(r)
