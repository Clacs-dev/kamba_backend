"""
Rotas da cultura organizacional (secção 6) — inquéritos-pulso anónimos.
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

router = APIRouter(prefix="/surveys", tags=["culture"])

MANAGE_ROLES = (UserRole.CAPITAL_HUMANO, UserRole.ADMINISTRACAO)
MIN_RESPONSES = 5


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
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    survey = Survey(
        company_id=current_user.company_id,
        title=payload.title,
        dimensions=json.dumps(payload.dimensions),
    )
    db.add(survey)
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
    survey = _get_survey_or_404(db, current_user.company_id, survey_id)
    if survey.status != SurveyStatus.ABERTO:
        raise HTTPException(status_code=409, detail="Este inquérito está fechado.")

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

    valid_dims = set(json.loads(survey.dimensions))
    for dim, val in payload.answers.items():
        if dim not in valid_dims:
            raise HTTPException(status_code=422, detail=f"Dimensão inválida: {dim}.")
        if not (1 <= val <= 5):
            raise HTTPException(status_code=422, detail="As respostas devem estar entre 1 e 5.")

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
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    survey = _get_survey_or_404(db, current_user.company_id, survey_id)
    survey.status = SurveyStatus.FECHADO
    db.commit()
    db.refresh(survey)
    return _to_out(survey)


@router.get("/{survey_id}/results", response_model=SurveyResults)
def get_results(
    survey_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    survey = _get_survey_or_404(db, current_user.company_id, survey_id)

    responses = (
        db.query(SurveyResponse)
        .filter(SurveyResponse.survey_id == survey.id)
        .all()
    )
    count = len(responses)

    if count < MIN_RESPONSES:
        return SurveyResults(
            survey_id=survey.id,
            response_count=count,
            released=False,
            results={},
            note=f"Resultados ocultados: são necessárias pelo menos {MIN_RESPONSES} respostas para proteger o anonimato.",
        )

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
    )