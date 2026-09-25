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
    CultureDimensionsEvolution, DimensionEvolution, DimensionCyclePoint,
)
from app.api.deps import get_current_user, require_roles
from app.services.audit import audit

router = APIRouter(prefix="/surveys", tags=["culture"])

# Criação/fecho de pulses: Capital Humano e Administração, mais o Director.
SURVEY_ROLES = (UserRole.CAPITAL_HUMANO, UserRole.ADMINISTRACAO, UserRole.DIRECTOR)
MANAGE_ROLES = (UserRole.CAPITAL_HUMANO, UserRole.ADMINISTRACAO, UserRole.ADMIN)
MIN_RESPONSES = 5  # limiar de anonimato (secção 6)


def _participation_stats(
    db: Session, company_id: int, survey_id: int
) -> tuple[int, int, float | None]:
    """
    Participação de um pulse, calculada dos dados reais (nunca preenchida à mão):
    colaboradores que responderam sobre o universo de colaboradores que PODEM
    responder. A gestão cria/gesta os pulses mas não participa, por isso fica
    excluída do universo — assim a taxa reflecte quem realmente devia responder.
    """
    eligible_ids = (
        db.query(User.id)
        .filter(
            User.company_id == company_id,
            User.is_active.is_(True),
            User.role.notin_([r for r in SURVEY_ROLES]),
        )
        .scalar_subquery()
    )
    universe = (
        db.query(User)
        .filter(User.id.in_(eligible_ids))
        .count()
    )
    participation_count = (
        db.query(SurveyParticipation)
        .filter(
            SurveyParticipation.survey_id == survey_id,
            SurveyParticipation.user_id.in_(eligible_ids),
        )
        .count()
    )
    rate = (
        round(participation_count * 100 / universe, 1) if universe else None
    )
    return participation_count, universe, rate


# Dimensões do pulse que medem a recomendação ("Recomendaria a empresa...").
RECOMMEND_KEYWORDS = ("recomend", "recommend")


def _enps_for_survey(
    db: Session, survey_id: int
) -> tuple[int | None, int, int, int]:
    """
    eNPS calculado das respostas do pulse (nunca preenchido à mão).

    A pergunta de recomendação (dimensão que contém "recomend") na escala 1–5
    é mapeada para a lógica clássica 0–10:
      1–2 → Detrator  |  3 → Neutro  |  4–5 → Promotor
      eNPS = (Promotores − Detratores) / totais × 100   (−100 .. +100)
    """
    responses = (
        db.query(SurveyResponse)
        .filter(SurveyResponse.survey_id == survey_id)
        .all()
    )
    promoters = neutrals = detractors = 0
    for r in responses:
        ans = json.loads(r.answers)
        for dim, val in ans.items():
            brand = dim.strip().lower()
            if any(k in brand for k in RECOMMEND_KEYWORDS) and isinstance(val, int):
                if val <= 2:
                    detractors += 1
                elif val == 3:
                    neutrals += 1
                else:
                    promoters += 1
                break  # uma resposta por colaborador
    total = promoters + neutrals + detractors
    score = round((promoters - detractors) * 100 / total) if total else None
    return score, promoters, neutrals, detractors


def _get_survey_or_404(db: Session, company_id: int, survey_id: int) -> Survey:
    s = (
        db.query(Survey)
        .filter(Survey.id == survey_id, Survey.company_id == company_id)
        .first()
    )
    if s is None:
        raise HTTPException(status_code=404, detail="Inquérito não encontrado.")
    return s


def _to_out(s: Survey, participated: bool = False) -> SurveyOut:
    return SurveyOut(
        id=s.id, company_id=s.company_id, title=s.title,
        dimensions=json.loads(s.dimensions), status=s.status, created_at=s.created_at,
        participated=participated,
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
    participated_ids = {
        p.survey_id
        for p in db.query(SurveyParticipation).filter(
            SurveyParticipation.company_id == current_user.company_id,
            SurveyParticipation.user_id == current_user.id,
        ).all()
    }
    return [_to_out(s, s.id in participated_ids) for s in surveys]


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

    # A gestão cria/gesta os pulses, mas não responde (são dos colaboradores).
    if current_user.role in SURVEY_ROLES:
        raise HTTPException(
            status_code=403,
            detail="A gestão não participa no pulse — apenas os colaboradores respondem.",
        )

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


@router.delete("/{survey_id}")
def delete_survey(
    survey_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*SURVEY_ROLES)),
):
    """Elimina um pulse e as respostas/participações associadas."""
    survey = _get_survey_or_404(db, current_user.company_id, survey_id)
    db.query(SurveyResponse).filter(SurveyResponse.survey_id == survey.id).delete()
    db.query(SurveyParticipation).filter(SurveyParticipation.survey_id == survey.id).delete()
    audit(db, actor=current_user, action="cultura.pulse_eliminado",
          detail=f"Inquérito-pulso '{survey.title}' eliminado.")
    db.delete(survey)
    db.commit()
    return {"detail": "Inquérito eliminado."}


# ---------- Evolução das dimensões por ciclo (calculada das respostas) ----------

@router.get("/culture-report/evolution", response_model=CultureDimensionsEvolution)
def culture_evolution(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Evolução das dimensões de cultura através dos ciclos/pulses.
    As % são calculadas automaticamente das respostas reais: para cada pulse,
    média da dimensão na escala 1..5 normalizada em percentagem (media/5*100).
    Devolve uma coluna por ciclo (do mais antigo ao mais recente).
    Qualquer perfil da empresa pode consultar; o anonimato mantém-se porque só
    se mostram médias agregadas.
    """
    company_id = current_user.company_id
    surveys = (
        db.query(Survey)
        .filter(Survey.company_id == company_id)
        .order_by(Survey.created_at.asc())
        .all()
    )

    per_survey: list[dict[str, float]] = []
    cycle_labels: list[str] = []
    for s in surveys:
        responses = (
            db.query(SurveyResponse)
            .filter(SurveyResponse.survey_id == s.id)
            .all()
        )
        if not responses:
            continue
        dims_js = json.loads(s.dimensions)
        totals = {d: 0 for d in dims_js}
        counts = {d: 0 for d in dims_js}
        for r in responses:
            ans = json.loads(r.answers)
            for d, v in ans.items():
                if d in totals:
                    totals[d] += v
                    counts[d] += 1
        pct = {}
        for d in dims_js:
            if counts[d] > 0:
                media = totals[d] / counts[d]
                pct[d] = round(media / 5 * 100, 1)
        per_survey.append(pct)
        cycle_labels.append(s.title)

    if not cycle_labels:
        return CultureDimensionsEvolution(dimensions=[], cycles=[])

    all_dims: list[str] = []
    for p in per_survey:
        for d in p:
            if d not in all_dims:
                all_dims.append(d)

    dimensions = []
    for d in all_dims:
        points = []
        for i, p in enumerate(per_survey):
            points.append(DimensionCyclePoint(
                survey_id=0,
                cycle_label=cycle_labels[i],
                value=p.get(d, None),  # type: ignore[arg-type]
            ))
        latest = next((pt.value for pt in reversed(points) if pt.value is not None), None)
        dimensions.append(DimensionEvolution(name=d, points=points, latest=latest))

    return CultureDimensionsEvolution(dimensions=dimensions, cycles=cycle_labels)


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

    # Participação (secção 6): universo de colaboradores que podem responder,
    # participações registadas e taxa — calculadas dos dados reais, nunca estáticas.
    participation_count, universe, participation_rate = _participation_stats(
        db, current_user.company_id, survey.id
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
            enps_score=0,
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
    enps_score, enps_promoters, enps_neutrals, enps_detractors = _enps_for_survey(
        db, survey.id
    )
    return SurveyResults(
        survey_id=survey.id,
        response_count=count,
        released=True,
        results=results,
        note="Resultados agregados.",
        participation_count=participation_count,
        universe=universe,
        participation_rate=participation_rate,
        enps_score=enps_score,
        enps_promoters=enps_promoters,
        enps_neutrals=enps_neutrals,
        enps_detractors=enps_detractors,
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
    out = _report_to_out(r)

    # Participação calculada automaticamente do pulse mais recente: colaboradores
    # que responderam vs. universo de quem podia responder. Nunca estática.
    latest = (
        db.query(Survey)
        .filter(Survey.company_id == current_user.company_id)
        .order_by(Survey.created_at.desc())
        .first()
    )
    if latest is not None:
        participation_count, universe, participation_rate = _participation_stats(
            db, current_user.company_id, latest.id
        )
        out.participation_count = participation_count
        out.universe = universe
        out.participation_rate = participation_rate

        enps_score, enps_promoters, enps_neutrals, enps_detractors = _enps_for_survey(
            db, latest.id
        )
        out.enps_score = enps_score
        out.enps_promoters = enps_promoters
        out.enps_neutrals = enps_neutrals
        out.enps_detractors = enps_detractors

    return out


@router.put("/culture-report/data", response_model=CultureReportOut)
def put_culture_report(
    payload: CultureReportIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CAPITAL_HUMANO, UserRole.ADMINISTRACAO, UserRole.ADMIN)),
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
