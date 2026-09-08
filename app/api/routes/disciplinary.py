"""
Rotas do processo disciplinar (secção 4) — a segunda máquina de seis fases.

Fluxo (4.1):
  1. INSTAURACAO           -> instrutor abre (factos, antecedentes)
  2. NOTA_CULPA            -> instrutor emite nota de culpa; arguido assina conhecimento
  3. DEFESA                -> arguido submete defesa escrita
  4. DECISAO               -> instrutor emite decisão (medida ou arquivamento)
  5. CONHECIMENTO_DECISAO  -> arguido assina conhecimento da decisão
  6. ARQUIVADO             -> processo encerrado e averbado

Regra do manual: não se pode saltar fases; nenhuma medida é averbada sem o
processo percorrer todas as fases. Instrução compete ao Capital Humano.
Isolamento por company_id.
"""
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.models.enums import UserRole, DisciplinaryPhase, DisciplinaryOutcome
from app.models.disciplinary import DisciplinaryProcess, DisciplinaryCommitteeMember
from app.schemas.disciplinary import (
    ProcessCreate, ChargeNoteRequest, DefenseRequest, DecisionRequest, ProcessOut,
    CommitteeSetRequest, CommitteeMemberOut,
)
from app.api.deps import get_current_user, require_roles
from app.services.notifications import notify
from app.services.audit import audit

router = APIRouter(prefix="/disciplinary", tags=["disciplinary"])

# Por decisão do cliente, todos os perfis podem instruir processos por enquanto.
INSTRUCTOR_ROLES = tuple(UserRole)

# Quem pode compor a comissão disciplinar de um processo — mesmo grupo que
# gere pessoas noutros módulos (collaborators.py, admin.py), mais restrito
# que INSTRUCTOR_ROLES acima (esse é um placeholder amplo e temporário).
COMMITTEE_MANAGE_ROLES = (UserRole.CAPITAL_HUMANO, UserRole.ADMINISTRACAO, UserRole.ADMIN)


def _now():
    return datetime.now(timezone.utc)


# Prazo legal de defesa do arguido (Lei Geral do Trabalho): 10 dias úteis
# a contar da notificação da nota de culpa.
DEFENSE_DEADLINE_DAYS = 10


def _add_business_days(start: datetime, days: int) -> datetime:
    """Soma 'days' dias úteis (seg-sex), ignorando fins de semana."""
    d = start
    added = 0
    while added < days:
        d = d + timedelta(days=1)
        if d.weekday() < 5:
            added += 1
    return d


def _get_or_404(db: Session, company_id: int, process_id: int) -> DisciplinaryProcess:
    p = (
        db.query(DisciplinaryProcess)
        .filter(DisciplinaryProcess.id == process_id, DisciplinaryProcess.company_id == company_id)
        .first()
    )
    if p is None:
        raise HTTPException(status_code=404, detail="Processo não encontrado.")
    return p


def _require_phase(p: DisciplinaryProcess, expected: DisciplinaryPhase):
    if p.phase != expected:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ação inválida nesta fase. O processo está em '{p.phase.value}', esperava-se '{expected.value}'.",
        )


def _committee_map(db: Session, process_ids: list[int]) -> dict[int, list[CommitteeMemberOut]]:
    """Membros da comissão de vários processos, numa só query (evita N+1)."""
    if not process_ids:
        return {}
    rows = (
        db.query(DisciplinaryCommitteeMember, User)
        .join(User, User.id == DisciplinaryCommitteeMember.user_id)
        .filter(DisciplinaryCommitteeMember.process_id.in_(process_ids))
        .all()
    )
    result: dict[int, list[CommitteeMemberOut]] = {}
    for member, user in rows:
        result.setdefault(member.process_id, []).append(
            CommitteeMemberOut(id=user.id, full_name=user.full_name)
        )
    return result


def _process_out(db: Session, p: DisciplinaryProcess) -> ProcessOut:
    out = ProcessOut.model_validate(p)
    out.committee_members = _committee_map(db, [p.id]).get(p.id, [])
    return out


def _processes_out(db: Session, processes: list[DisciplinaryProcess]) -> list[ProcessOut]:
    cmap = _committee_map(db, [p.id for p in processes])
    saida = []
    for p in processes:
        out = ProcessOut.model_validate(p)
        out.committee_members = cmap.get(p.id, [])
        saida.append(out)
    return saida


# ---------- Fase 1: Instauração (instrutor) ----------

@router.post("", response_model=ProcessOut, status_code=status.HTTP_201_CREATED)
def open_process(
    payload: ProcessCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*INSTRUCTOR_ROLES)),
):
    accused = (
        db.query(User)
        .filter(User.id == payload.accused_id, User.company_id == current_user.company_id)
        .first()
    )
    if accused is None:
        raise HTTPException(status_code=404, detail="Arguido não encontrado nesta empresa.")

    p = DisciplinaryProcess(
        company_id=current_user.company_id,
        accused_id=payload.accused_id,
        instructor_id=current_user.id,
        reference=payload.reference,
        imputed_facts=payload.imputed_facts,
        disciplinary_record=payload.disciplinary_record,
        phase=DisciplinaryPhase.INSTAURACAO,
    )
    db.add(p)
    audit(db, actor=current_user, action="disciplina.instaurado",
          detail=f"Processo {p.reference} instaurado contra {accused.full_name}.")
    db.commit()
    db.refresh(p)
    return _process_out(db, p)


@router.get("", response_model=list[ProcessOut])
def list_processes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Lista os processos disciplinares:
    - Instrutores (CH, Administração, Comissão) veem todos os da empresa.
    - O arguido vê apenas os seus.
    """
    query = db.query(DisciplinaryProcess).filter(
        DisciplinaryProcess.company_id == current_user.company_id
    )
    if current_user.role not in INSTRUCTOR_ROLES:
        query = query.filter(DisciplinaryProcess.accused_id == current_user.id)
    return _processes_out(db, query.order_by(DisciplinaryProcess.id.desc()).all())


@router.get("/{process_id}", response_model=ProcessOut)
def get_process(
    process_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = _get_or_404(db, current_user.company_id, process_id)
    # O arguido pode ver o seu processo; os instrutores veem os da empresa.
    if current_user.role not in INSTRUCTOR_ROLES and p.accused_id != current_user.id:
        raise HTTPException(status_code=403, detail="Sem acesso a este processo.")
    return _process_out(db, p)


# ---------- Comissão disciplinar (alteração 11) ----------

@router.post("/{process_id}/committee", response_model=ProcessOut)
def set_committee(
    process_id: int,
    payload: CommitteeSetRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*COMMITTEE_MANAGE_ROLES)),
):
    """
    Define (ou substitui) a comissão disciplinar do processo: exactamente 3
    colaboradores com perfil Director, da mesma empresa, que não sejam o
    próprio arguido. Pode ser chamado enquanto o processo não estiver
    arquivado.
    """
    p = _get_or_404(db, current_user.company_id, process_id)
    if p.phase == DisciplinaryPhase.ARQUIVADO:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Não é possível alterar a comissão de um processo já arquivado.",
        )

    if p.accused_id in payload.member_ids:
        raise HTTPException(
            status_code=422,
            detail="O arguido não pode integrar a comissão disciplinar do seu próprio processo.",
        )

    membros = (
        db.query(User)
        .filter(
            User.id.in_(payload.member_ids),
            User.company_id == current_user.company_id,
            User.role == UserRole.DIRECTOR,
        )
        .all()
    )
    if len(membros) != 3:
        raise HTTPException(
            status_code=422,
            detail="Os 3 membros da comissão têm de ser colaboradores com perfil Director desta empresa.",
        )

    db.query(DisciplinaryCommitteeMember).filter(
        DisciplinaryCommitteeMember.process_id == p.id
    ).delete()
    for membro in membros:
        db.add(DisciplinaryCommitteeMember(process_id=p.id, user_id=membro.id))

    audit(db, actor=current_user, action="disciplina.comissao_definida",
          detail=f"Comissão disciplinar do processo {p.reference} definida: "
                 + ", ".join(m.full_name for m in membros) + ".")
    db.commit()
    db.refresh(p)
    return _process_out(db, p)


# ---------- Fase 2: Nota de culpa (instrutor emite) ----------

@router.post("/{process_id}/charge-note", response_model=ProcessOut)
def issue_charge_note(
    process_id: int,
    payload: ChargeNoteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*INSTRUCTOR_ROLES)),
):
    p = _get_or_404(db, current_user.company_id, process_id)
    _require_phase(p, DisciplinaryPhase.INSTAURACAO)

    p.charge_note = payload.charge_note
    p.preventive_suspension = payload.preventive_suspension
    p.defense_deadline = _add_business_days(_now(), DEFENSE_DEADLINE_DAYS).date()
    p.phase = DisciplinaryPhase.NOTA_CULPA  # notificada -> aguarda conhecimento do arguido
    notify(
        db, company_id=p.company_id, user_id=p.accused_id,
        title="Nota de culpa",
        message=f"Foi emitida uma nota de culpa no seu processo disciplinar. Deve lê-la e assinar a tomada de conhecimento; tem 10 dias úteis para apresentar defesa escrita.",
        category="disciplina", link=f"/disciplinary/{p.id}",
    )
    audit(db, actor=current_user, action="disciplina.nota_culpa",
          detail=f"Nota de culpa emitida no processo {p.reference} "
                 f"({'com' if payload.preventive_suspension else 'sem'} suspensão preventiva).")
    db.commit()
    db.refresh(p)
    return _process_out(db, p)


# ---------- Fase 2->3: Arguido assina conhecimento da nota de culpa ----------

@router.post("/{process_id}/acknowledge-charge", response_model=ProcessOut)
def acknowledge_charge(
    process_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = _get_or_404(db, current_user.company_id, process_id)
    _require_phase(p, DisciplinaryPhase.NOTA_CULPA)
    if p.accused_id != current_user.id:
        raise HTTPException(status_code=403, detail="Só o arguido pode assinar a tomada de conhecimento.")

    p.charge_ack_at = _now()
    p.phase = DisciplinaryPhase.DEFESA  # -> pode apresentar defesa
    audit(db, actor=current_user, action="disciplina.conhecimento_nota_culpa",
          detail=f"Arguido tomou conhecimento da nota de culpa no processo {p.reference}.")
    db.commit()
    db.refresh(p)
    return _process_out(db, p)


# ---------- Fase 3: Defesa (arguido submete) ----------

@router.post("/{process_id}/defense", response_model=ProcessOut)
def submit_defense(
    process_id: int,
    payload: DefenseRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = _get_or_404(db, current_user.company_id, process_id)
    _require_phase(p, DisciplinaryPhase.DEFESA)
    if p.accused_id != current_user.id:
        raise HTTPException(status_code=403, detail="Só o arguido pode submeter a defesa.")
    if p.defense_deadline and _now().date() > p.defense_deadline:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="O prazo de defesa (10 dias úteis) já terminou.",
        )

    p.defense_text = payload.defense_text
    p.defense_submitted_at = _now()
    p.phase = DisciplinaryPhase.DECISAO  # -> aguarda decisão do instrutor
    audit(db, actor=current_user, action="disciplina.defesa",
          detail=f"Defesa submetida no processo {p.reference}.")
    db.commit()
    db.refresh(p)
    return _process_out(db, p)


# ---------- Fase 4: Decisão (instrutor emite) ----------

@router.post("/{process_id}/decision", response_model=ProcessOut)
def issue_decision(
    process_id: int,
    payload: DecisionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*INSTRUCTOR_ROLES)),
):
    p = _get_or_404(db, current_user.company_id, process_id)
    _require_phase(p, DisciplinaryPhase.DECISAO)

    p.decision_text = payload.decision_text
    p.outcome = payload.outcome
    p.phase = DisciplinaryPhase.CONHECIMENTO_DECISAO  # -> aguarda conhecimento do arguido
    notify(
        db, company_id=p.company_id, user_id=p.accused_id,
        title="Decisão disciplinar",
        message="Foi emitida a decisão do seu processo disciplinar. Deve lê-la e assinar a tomada de conhecimento.",
        category="disciplina", link=f"/disciplinary/{p.id}",
    )
    audit(db, actor=current_user, action="disciplina.decisao",
          detail=f"Decisão emitida no processo {p.reference}.")
    db.commit()
    db.refresh(p)
    return _process_out(db, p)


# ---------- Fase 5->6: Arguido assina conhecimento da decisão -> arquiva ----------

@router.post("/{process_id}/acknowledge-decision", response_model=ProcessOut)
def acknowledge_decision(
    process_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = _get_or_404(db, current_user.company_id, process_id)
    _require_phase(p, DisciplinaryPhase.CONHECIMENTO_DECISAO)
    if p.accused_id != current_user.id:
        raise HTTPException(status_code=403, detail="Só o arguido pode assinar o conhecimento da decisão.")

    p.decision_ack_at = _now()
    p.phase = DisciplinaryPhase.ARQUIVADO  # encerrado e averbado
    audit(db, actor=current_user, action="disciplina.arquivado",
          detail=f"Processo {p.reference} encerrado e averbado após conhecimento da decisão.")
    db.commit()
    db.refresh(p)
    return _process_out(db, p)


# ---------- Consultas ----------

@router.get("/collaborator/{accused_id}", response_model=list[ProcessOut])
def list_processes_of_collaborator(
    accused_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*INSTRUCTOR_ROLES)),
):
    """O instrutor consulta o cadastro disciplinar de um colaborador."""
    return _processes_out(db, (
        db.query(DisciplinaryProcess)
        .filter(
            DisciplinaryProcess.company_id == current_user.company_id,
            DisciplinaryProcess.accused_id == accused_id,
        )
        .order_by(DisciplinaryProcess.created_at.desc())
        .all()
    ))


# ---------- PDF da peça disciplinar ----------

from fastapi import Response
from app.models.company import Company
from app.services.report_pdf import gerar_pdf_peca_disciplinar


@router.get("/{process_id}/pdf")
def disciplinary_pdf(
    process_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Gera o PDF da peça disciplinar (factos, nota de culpa, decisão)."""
    p = _get_or_404(db, current_user.company_id, process_id)
    # Instrutores e o próprio arguido podem descarregar.
    if current_user.role not in INSTRUCTOR_ROLES and p.accused_id != current_user.id:
        raise HTTPException(status_code=403, detail="Sem acesso a este processo.")

    accused = db.query(User).filter(User.id == p.accused_id).first()
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    pdf_bytes = gerar_pdf_peca_disciplinar(
        p,
        accused_name=accused.full_name if accused else f"#{p.accused_id}",
        company_name=company.name if company else "Empresa",
    )
    filename = f"processo_{p.reference}.pdf".replace(" ", "_").replace("/", "-")
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
