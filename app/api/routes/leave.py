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
  GET  /leave/map?ano=            -> mapa anual (reservado)
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.models.enums import UserRole, LeaveType, LeaveStatus
from app.models.leave import LeaveRequest
from app.api.deps import get_current_user, require_roles
from app.services.notifications import notify
from app.services.audit import audit
from app.services.cloudinary_upload import upload_file

router = APIRouter(prefix="/leave", tags=["leave"])

ANNUAL = 22  # dias de férias por ano
CH_ROLES = (UserRole.CAPITAL_HUMANO, UserRole.ADMINISTRACAO)


def _count_days(a: date, b: date) -> int:
    return (b - a).days + 1


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
    """Saldo: direito (22), gozados (aprovadas passadas/averbadas), marcados (aprovadas futuras), disponiveis."""
    year = ano or date.today().year
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
    disponiveis = ANNUAL - gozados - marcados
    return {"direito": ANNUAL, "gozados": gozados, "marcados": marcados, "disponiveis": disponiveis}


# ---------- 1.2 Listar ----------

@router.get("/requests")
def list_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Colaborador vê os seus; director vê a equipa; CH/admin veem todos."""
    q = db.query(LeaveRequest).filter(LeaveRequest.company_id == current_user.company_id)
    if current_user.role == UserRole.COLABORADOR:
        q = q.filter(LeaveRequest.collaborator_id == current_user.id)
    # director e CH/admin veem todos os da empresa (a equipa do director = empresa, simplificação)
    rows = q.order_by(LeaveRequest.id.desc()).all()
    return [_out(db, r) for r in rows]


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
        days=_count_days(inicio, fim),
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


# ---------- 1.8 Mapa anual (reservado) ----------

@router.get("/map")
def annual_map(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*CH_ROLES)),
    ano: int | None = None,
):
    year = ano or date.today().year
    rows = (
        db.query(LeaveRequest)
        .filter(
            LeaveRequest.company_id == current_user.company_id,
            LeaveRequest.averbado == True,  # noqa: E712
        )
        .all()
    )
    return [_out(db, r) for r in rows if r.start_date.year == year]
