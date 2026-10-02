"""
Rotas de Férias & Ausências — alinhadas ao contrato do frontend.

Endpoints:
  GET  /leave/me/balance          -> saldo {direito, gozados, marcados, disponiveis}
  GET  /leave/requests            -> lista filtrada por perfil
  POST /leave/requests            -> criar (multipart, com documento opcional)
  POST /leave/requests/{id}/approve   -> director aprova
  POST /leave/requests/{id}/reject    -> director recusa (motivo)
  POST /leave/maternity           -> CH regista maternidade (multipart)
  POST /leave/requests/{id}/register  -> CH averba no mapa
  GET  /leave/map?ano=            -> mapa anual (consolidado para CH, do departamento para director)
  GET  /leave/entitlements?ano=   -> direito a ferias por colaborador (22 dias por ano de ferias)
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.models.enums import UserRole, LeaveType, LeaveStatus
from app.models.leave import LeaveRequest
from app.models.employee_profile import EmployeeProfile
from app.api.deps import get_current_user, require_roles
from app.services.notifications import notify
from app.services.audit import audit
from app.services.cloudinary_upload import upload_file
from app.services.leave_entitlement import (
    ANNUAL_DAYS,
    entitlement_for_year,
    finalise,
)

router = APIRouter(prefix="/leave", tags=["leave"])

ANNUAL = ANNUAL_DAYS  # dias de ferias por ano de ferias (22)
CH_ROLES = (UserRole.CAPITAL_HUMANO, UserRole.ADMINISTRACAO, UserRole.ADMIN)
MAP_ROLES = (UserRole.DIRECTOR, UserRole.CAPITAL_HUMANO, UserRole.ADMINISTRACAO, UserRole.ADMIN)


def _count_days(a: date, b: date) -> int:
    return (b - a).days + 1


def _norm_dept(valor: str | None) -> str:
    """Normaliza a Direccao para comparacao (minusculas, espacos colapsados)."""
    return " ".join((valor or "").split()).casefold()


def _perfil(db: Session, user_id: int) -> EmployeeProfile | None:
    return db.query(EmployeeProfile).filter(EmployeeProfile.user_id == user_id).first()


def _direccao(db: Session, user: User) -> str:
    p = _perfil(db, user.id)
    return (p.department or "") if p else ""


def _escopo(db: Session, user: User) -> list[User]:
    """
    Colaboradores visiveis para o utilizador.

    Capital Humano / administracao veem a empresa inteira; cada director ve apenas
    os colaboradores da sua propria Direccao (campo 'department' da ficha, tambem
    preenchido na ficha do proprio director).
    """
    q = db.query(User).filter(
        User.company_id == user.company_id,
        User.is_active.is_(True),
        User.role == UserRole.COLABORADOR,
    )
    if user.role != UserRole.DIRECTOR:
        return q.order_by(User.full_name).all()

    alvo = _norm_dept(_direccao(db, user))
    if not alvo:
        # Director sem Direccao definida na ficha -> nao tem equipa atribuivel.
        return []
    return [u for u in q.order_by(User.full_name).all() if _norm_dept(_direccao(db, u)) == alvo]


def _out(db: Session, r: LeaveRequest) -> dict:
    """Serializa um pedido no formato do contrato (com collaborator_name)."""
    nome = None
    u = db.query(User).filter(User.id == r.collaborator_id).first()
    if u:
        nome = u.full_name
    return {
        "id": r.id,
        "collaborator_id": r.collaborator_id,
        "collaborator_name": nome,
        "type": r.leave_type.value,
        "start_date": r.start_date.isoformat(),
        "end_date": r.end_date.isoformat(),
        "days": r.days,
        "reason": r.reason,
        "status": r.status.value,
        "document_name": r.document_name,
        "document_url": r.document_url,
        "averbado": r.averbado,
    }


def _get_or_404(db, company_id, rid) -> LeaveRequest:
    r = db.query(LeaveRequest).filter(
        LeaveRequest.id == rid, LeaveRequest.company_id == company_id
    ).first()
    if not r:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")
    return r


# ---------- 1.1 Saldo ----------

@router.get("/me/balance")
def my_balance(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ano: int | None = None,
):
    """Saldo do ano: direito (22 por ano de ferias), gozados, marcados, disponiveis."""
    year = ano or date.today().year
    adm = None
    p = _perfil(db, current_user.id)
    if p:
        adm = p.admission_date
    dados = entitlement_for_year(adm, year)

    ferias = (
        db.query(LeaveRequest)
        .filter(
            LeaveRequest.company_id == current_user.company_id,
            LeaveRequest.collaborator_id == current_user.id,
            LeaveRequest.leave_type == LeaveType.FERIAS,
            LeaveRequest.status == LeaveStatus.APROVADA,
        )
        .all()
    )
    hoje = date.today()
    gozados = sum(r.days for r in ferias if r.start_date.year == year and r.end_date < hoje)
    marcados = sum(r.days for r in ferias if r.start_date.year == year and r.end_date >= hoje)
    finalise(dados, gozados, marcados)
    return dados


# ---------- 1.1b Direito a ferias por colaborador (CH / director) ----------

def _consumo(db: Session, company_id: int, ano: int, collaborator_id: int) -> tuple[int, int, int]:
    """(gozados, marcados, em_curso) de ferias aprovadas dentro do ano."""
    hoje = date.today()
    gozados = marcados = em_curso = 0
    linhas = (
        db.query(LeaveRequest)
        .filter(
            LeaveRequest.company_id == company_id,
            LeaveRequest.collaborator_id == collaborator_id,
            LeaveRequest.leave_type == LeaveType.FERIAS,
            LeaveRequest.status == LeaveStatus.APROVADA,
        )
        .all()
    )
    for r in linhas:
        if r.start_date.year != ano and r.end_date.year != ano:
            continue
        if r.end_date < hoje:
            gozados += r.days
        elif r.start_date > hoje:
            marcados += r.days
        else:
            em_curso += r.days
    return gozados, marcados, em_curso


@router.get("/entitlements")
def list_entitlements(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MAP_ROLES)),
    ano: int | None = None,
):
    """Direito a ferias de cada colaborador do escopo, lido da data de admissao."""
    year = ano or date.today().year
    linhas = []
    for u in _escopo(db, current_user):
        p = _perfil(db, u.id)
        adm = p.admission_date if p else None
        dados = entitlement_for_year(adm, year)
        g, m, c = _consumo(db, current_user.company_id, year, u.id)
        finalise(dados, g, m, c)
        linhas.append({
            "collaborator_id": u.id,
            "full_name": u.full_name,
            "department": (p.department if p else None),
            "admission_date": adm.isoformat() if adm else None,
            **dados,
        })
    return {
        "ano": year,
        "scope": "departamento" if current_user.role == UserRole.DIRECTOR else "empresa",
        "direccao": _direccao(db, current_user) if current_user.role == UserRole.DIRECTOR else None,
        "direito_anual": ANNUAL,
        "colaboradores": linhas,
    }


# ---------- 1.2 Listar ----------

@router.get("/requests")
def list_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Colaborador ve os seus; director ve a equipa da sua Direccao; CH/admin veem todos."""
    q = db.query(LeaveRequest).filter(LeaveRequest.company_id == current_user.company_id)
    if current_user.role == UserRole.COLABORADOR:
        q = q.filter(LeaveRequest.collaborator_id == current_user.id)
    elif current_user.role == UserRole.DIRECTOR:
        ids = [u.id for u in _escopo(db, current_user)]
        q = q.filter(LeaveRequest.collaborator_id.in_(ids or [-1]))
    rows = q.order_by(LeaveRequest.id.desc()).all()
    return [_out(db, r) for r in rows]


def _pertence_a_equipa(db: Session, user: User, r: LeaveRequest) -> bool:
    """Um director so gere pedidos de colaboradores da sua Direccao."""
    if user.role != UserRole.DIRECTOR:
        return True
    return r.collaborator_id in [u.id for u in _escopo(db, user)]


# ---------- 1.3 Criar (multipart) ----------

@router.post("/requests", status_code=201)
async def create_request(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tipo: str = Form(...),
    inicio: date = Form(...),
    fim: date = Form(...),
    motivo: str = Form(...),
    documento: UploadFile | None = File(default=None),
):
    """O colaborador cria um pedido de férias ou falta (com documento opcional)."""
    if tipo not in ("ferias", "falta"):
        raise HTTPException(status_code=422, detail="Tipo inválido (ferias ou falta).")
    if fim < inicio:
        raise HTTPException(status_code=422, detail="A data de fim não pode ser anterior ao início.")

    # Direito a férias: o sistema lê a data de admissão e diz se o colaborador
    # pode pedir férias no ano pedido (22 dias úteis por ano de férias).
    dias = _count_days(inicio, fim)
    if tipo == "ferias":
        ano = inicio.year
        p = _perfil(db, current_user.id)
        dados = entitlement_for_year(p.admission_date if p else None, ano)
        g, m, c = _consumo(db, current_user.company_id, ano, current_user.id)
        finalise(dados, g, m, c)
        if dados["direito"] <= 0:
            adm_txt = p.admission_date.isoformat() if p and p.admission_date else "sem data de admissão"
            raise HTTPException(
                status_code=422,
                detail=f"Em {ano} não tem direito a férias (admissão: {adm_txt}; "
                       f"o ano de férias {dados['ano_inicio']} a {dados['ano_fim']} "
                       f"não dá direito neste ano).",
            )
        if dias > dados["disponiveis"]:
            raise HTTPException(
                status_code=422,
                detail=f"Excede o saldo disponível: pediu {dias} dia(s) e tem "
                       f"{dados['disponiveis']} disponível(is) de {dados['direito']} em {ano}.",
            )

    doc_name, doc_url = None, None
    if documento is not None:
        conteudo = await documento.read()
        doc_name = documento.filename
        doc_url = upload_file(conteudo, documento.filename, folder="kamba/ausencias")

    # Máquina de estados do contrato:
    if tipo == "falta" and documento is not None:
        status = LeaveStatus.JUSTIFICADA  # falta com documento entra direto como justificada
    else:
        status = LeaveStatus.PENDENTE_DIR

    r = LeaveRequest(
        company_id=current_user.company_id,
        collaborator_id=current_user.id,
        leave_type=LeaveType(tipo),
        start_date=inicio, end_date=fim,
        days=dias,
        reason=motivo,
        document_name=doc_name, document_url=doc_url,
        status=status,
    )
    db.add(r)
    audit(db, actor=current_user, action="ausencia.pedido_criado",
          detail=f"{current_user.full_name} submeteu um pedido de {tipo} "
                 f"({inicio.isoformat()} a {fim.isoformat()}).")
    db.commit()
    db.refresh(r)

    # Notifica directores se precisa de aprovação.
    if status == LeaveStatus.PENDENTE_DIR:
        for d in db.query(User).filter(
            User.company_id == current_user.company_id, User.role == UserRole.DIRECTOR
        ).all():
            notify(db, company_id=current_user.company_id, user_id=d.id,
                   title="Pedido de ausência para aprovar",
                   message=f"{current_user.full_name} submeteu um pedido de {tipo}.",
                   category="ausencia", link="/ausencias")
        db.commit()
    return _out(db, r)


# ---------- 1.4 / 1.5 Aprovar / Recusar (director) ----------

@router.post("/requests/{rid}/approve")
def approve_request(
    rid: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.DIRECTOR)),
):
    r = _get_or_404(db, current_user.company_id, rid)
    if not _pertence_a_equipa(db, current_user, r):
        raise HTTPException(status_code=403, detail="Este pedido não é da sua Direcção.")
    if r.status != LeaveStatus.PENDENTE_DIR:
        raise HTTPException(status_code=400, detail="O pedido não está pendente do director.")
    r.status = LeaveStatus.APROVADA
    audit(db, actor=current_user, action="ausencia.aprovada",
          detail=f"Pedido #{r.id} ({r.leave_type.value}) de {r.collaborator_id} aprovado.")
    notify(db, company_id=current_user.company_id, user_id=r.collaborator_id,
           title="Ausência aprovada", message="A chefia aprovou o seu pedido de ausência.",
           category="ausencia", link="/portal")
    db.commit()
    db.refresh(r)
    return _out(db, r)


class RejectIn(BaseModel):
    motivo: str


@router.post("/requests/{rid}/reject")
def reject_request(
    rid: int,
    payload: RejectIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.DIRECTOR)),
):
    if not payload.motivo or len(payload.motivo.strip()) < 3:
        raise HTTPException(status_code=422, detail="O motivo é obrigatório (mín. 3 caracteres).")
    r = _get_or_404(db, current_user.company_id, rid)
    if not _pertence_a_equipa(db, current_user, r):
        raise HTTPException(status_code=403, detail="Este pedido não é da sua Direcção.")
    if r.status != LeaveStatus.PENDENTE_DIR:
        raise HTTPException(status_code=400, detail="O pedido não está pendente do director.")
    r.status = LeaveStatus.RECUSADA
    r.rejection_reason = payload.motivo
    audit(db, actor=current_user, action="ausencia.recusada",
          detail=f"Pedido #{r.id} recusado: {payload.motivo}.")
    notify(db, company_id=current_user.company_id, user_id=r.collaborator_id,
           title="Pedido de ausência recusado", message="A chefia recusou o seu pedido.",
           category="ausencia", link="/portal")
    db.commit()
    db.refresh(r)
    return _out(db, r)


# ---------- 1.6 Maternidade (CH, multipart) ----------

@router.post("/maternity", status_code=201)
async def register_maternity(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*CH_ROLES)),
    collaborator_id: int = Form(...),
    inicio: date = Form(...),
    fim: date = Form(...),
    motivo: str = Form(...),
    documento: UploadFile | None = File(default=None),
):
    """O Capital Humano regista uma licença de maternidade (entra já como aprovada)."""
    doc_name, doc_url = None, None
    if documento is not None:
        conteudo = await documento.read()
        doc_name = documento.filename
        doc_url = upload_file(conteudo, documento.filename, folder="kamba/maternidade")

    r = LeaveRequest(
        company_id=current_user.company_id,
        collaborator_id=collaborator_id,
        leave_type=LeaveType.MATERNIDADE,
        start_date=inicio, end_date=fim,
        days=_count_days(inicio, fim),
        reason=motivo,
        document_name=doc_name, document_url=doc_url,
        status=LeaveStatus.APROVADA,
    )
    db.add(r)
    audit(db, actor=current_user, action="ausencia.maternidade_registada",
          detail=f"Licença de maternidade do colaborador {collaborator_id} "
                 f"({inicio.isoformat()} a {fim.isoformat()}).")
    db.commit()
    db.refresh(r)

    # Regista no percurso do colaborador.
    from app.models.career import CareerEvent
    from app.models.enums import CareerEventType
    db.add(CareerEvent(
        company_id=current_user.company_id, collaborator_id=collaborator_id,
        event_type=CareerEventType.OUTRO, event_date=inicio,
        title="Licença de maternidade",
        description=f"Licença de maternidade de {inicio.isoformat()} a {fim.isoformat()}.",
    ))
    notify(db, company_id=current_user.company_id, user_id=collaborator_id,
           title="Licença de maternidade registada",
           message="A sua licença de maternidade foi registada.",
           category="ausencia", link="/portal")
    db.commit()
    return _out(db, r)


# ---------- 1.7 Doença prolongada (CH, multipart) ----------

@router.post("/prolonged-illness", status_code=201)
async def register_prolonged_illness(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*CH_ROLES)),
    collaborator_id: int = Form(...),
    inicio: date = Form(...),
    fim: date = Form(...),
    motivo: str = Form(...),
    documento: UploadFile | None = File(default=None),
):
    """O Capital Humano regista uma licença por doença prolongada (entra aprovada).
    Ajusta o ciclo de avaliação do colaborador (secção 3.1 / 8)."""
    doc_name, doc_url = None, None
    if documento is not None:
        conteudo = await documento.read()
        doc_name = documento.filename
        doc_url = upload_file(conteudo, documento.filename, folder="kamba/doenca")

    r = LeaveRequest(
        company_id=current_user.company_id,
        collaborator_id=collaborator_id,
        leave_type=LeaveType.DOENCA,
        start_date=inicio, end_date=fim,
        days=_count_days(inicio, fim),
        reason=motivo,
        document_name=doc_name, document_url=doc_url,
        status=LeaveStatus.APROVADA,
    )
    db.add(r)
    audit(db, actor=current_user, action="ausencia.doenca_registada",
          detail=f"Licença por doença prolongada do colaborador {collaborator_id} "
                 f"({inicio.isoformat()} a {fim.isoformat()}).")
    db.commit()
    db.refresh(r)

    # Regista no percurso do colaborador.
    from app.models.career import CareerEvent
    from app.models.enums import CareerEventType
    db.add(CareerEvent(
        company_id=current_user.company_id, collaborator_id=collaborator_id,
        event_type=CareerEventType.OUTRO, event_date=inicio,
        title="Licença por doença prolongada",
        description=f"Licença por doença prolongada de {inicio.isoformat()} a {fim.isoformat()}.",
    ))
    notify(db, company_id=current_user.company_id, user_id=collaborator_id,
           title="Licença por doença prolongada registada",
           message="A sua licença por doença prolongada foi registada.",
           category="ausencia", link="/portal")
    db.commit()
    return _out(db, r)


# ---------- 1.8 Averbar no mapa (CH) ----------

@router.post("/requests/{rid}/register")
def register_in_map(
    rid: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*CH_ROLES)),
):
    r = _get_or_404(db, current_user.company_id, rid)
    if r.status not in (LeaveStatus.APROVADA, LeaveStatus.JUSTIFICADA):
        raise HTTPException(status_code=400, detail="Só pedidos aprovados/justificados são averbados.")
    r.averbado = True
    audit(db, actor=current_user, action="ausencia.averbada",
          detail=f"Pedido #{r.id} averbado no mapa anual.")
    db.commit()
    db.refresh(r)
    return _out(db, r)


# ---------- 1.9 Mapa de ferias ----------

@router.get("/map")
def annual_map(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MAP_ROLES)),
    ano: int | None = None,
):
    """
    Mapa de ferias do ano.

    O Capital Humano recebe um unico mapa consolidado de toda a empresa; cada
    director recebe o mapa da sua propria Direccao. O direito de cada
    colaborador e lido da data de admissao (22 dias uteis por ano de ferias).
    """
    year = ano or date.today().year
    equipa = _escopo(db, current_user)
    ids = [u.id for u in equipa]

    pedidos = (
        db.query(LeaveRequest)
        .filter(
            LeaveRequest.company_id == current_user.company_id,
            LeaveRequest.collaborator_id.in_(ids or [-1]),
            LeaveRequest.status.in_((LeaveStatus.APROVADA, LeaveStatus.JUSTIFICADA)),
        )
        .order_by(LeaveRequest.start_date.asc())
        .all()
    )
    no_ano = [
        r for r in pedidos
        if r.start_date.year == year or r.end_date.year == year
    ]

    colaboradores = []
    for u in equipa:
        p = _perfil(db, u.id)
        dados = entitlement_for_year(p.admission_date if p else None, year)
        g, m, c = _consumo(db, current_user.company_id, year, u.id)
        finalise(dados, g, m, c)

        ferias = [r for r in no_ano
                  if r.collaborator_id == u.id and r.leave_type == LeaveType.FERIAS]
        outras = [r for r in no_ano
                  if r.collaborator_id == u.id and r.leave_type != LeaveType.FERIAS]

        colaboradores.append({
            "collaborator_id": u.id,
            "full_name": u.full_name,
            "department": p.department if p else None,
            "admission_date": p.admission_date.isoformat() if p and p.admission_date else None,
            **dados,
            "ferias": [_out(db, r) for r in ferias],
            "ausencias": [_out(db, r) for r in outras],
        })

    por_departamento: dict[str, int] = {}
    for linha in colaboradores:
        chave = linha["department"] or "Sem Direcção"
        por_departamento[chave] = por_departamento.get(chave, 0) + 1

    aviso = None
    if current_user.role == UserRole.DIRECTOR and not colaboradores:
        d = _direccao(db, current_user)
        aviso = (
            f"A sua Direcção «{d or 'por definir'}» não tem colaboradores associados. "
            "Confirme a Direcção escolhida na ficha de cada colaborador."
            if d else
            "A sua ficha não tem Direcção definida, por isso não é possível montar o mapa da equipa."
        )

    return {
        "ano": year,
        "scope": "departamento" if current_user.role == UserRole.DIRECTOR else "empresa",
        "direccao": _direccao(db, current_user) if current_user.role == UserRole.DIRECTOR else None,
        "direito_anual": ANNUAL,
        "aviso": aviso,
        "departamentos": sorted(por_departamento.items()),
        "colaboradores": colaboradores,
        "totais": {
            "colaboradores": len(colaboradores),
            "ferias": sum(len(c["ferias"]) for c in colaboradores),
            "ausencias": sum(len(c["ausencias"]) for c in colaboradores),
            "sem_direito": sum(1 for c in colaboradores if not c["pode_pedir"]),
        },
    }
