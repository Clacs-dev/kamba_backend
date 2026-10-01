"""
Rotas de gestão de colaboradores.

REGRA DE OURO (multi-tenant): todas as consultas filtram por
current_user.company_id — que vem do token, não de um parâmetro do cliente.
Um utilizador só vê e altera colaboradores da SUA empresa. Nunca se confia
num company_id enviado pelo cliente.

Permissões: criar, editar e desativar são reservados a Capital Humano e
Administração. Listar e ver são permitidos a esses mesmos perfis (os
colaboradores comuns têm o seu próprio portal, tratado noutro módulo).
"""
import logging
import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import hash_password
from app.models.user import User
from app.models.enums import UserRole
from app.schemas.collaborator import (
    CollaboratorCreate,
    CollaboratorUpdate,
    CollaboratorOut,
    CollaboratorCreatedOut,
    CollaboratorRowOut,
    PasswordResetOut,
)
from app.api.deps import require_roles, get_current_user

log = logging.getLogger(__name__)

router = APIRouter(prefix="/collaborators", tags=["collaborators"])

# Perfis com poder de gestão de pessoas.
MANAGE_ROLES = (UserRole.CAPITAL_HUMANO, UserRole.ADMINISTRACAO, UserRole.ADMIN)


def _extrair_ano(nome: str) -> int | None:
    """Extrai o ano (20XX) de um nome de ciclo, ex.: 'Avaliação 2025' -> 2025."""
    m = re.search(r"(20\d{2})", nome or "")
    return int(m.group(1)) if m else None


def _enriquecer_colaboradores(db: Session, current_user: User, usuarios: list[User]) -> list[CollaboratorRowOut]:
    """
    Constrói as linhas da tabela de colaboradores (estrutura KAMBA):

    - Ficha profissional: cargo, direção, ano de admissão, tags de situação.
    - Notas por ano: final_score dos ciclos de avaliação validados da empresa.
    - Situação: processo disciplinar em curso e/ou licença aprovada.
    - Nome curto da empresa (ex.: 'NZILA Comércio...' -> 'NZILA').
    """
    from app.models.employee_profile import EmployeeProfile
    from app.models.evaluation import Evaluation, EvaluationCycle, EvaluationPhase
    from app.models.disciplinary import DisciplinaryProcess, DisciplinaryPhase
    from app.models.leave import LeaveRequest, LeaveStatus, LeaveType
    from app.models.company import Company

    company_id = current_user.company_id
    if not usuarios:
        return []

    ids = [u.id for u in usuarios]

    perfis = {
        p.user_id: p
        for p in (
            db.query(EmployeeProfile)
            .filter(EmployeeProfile.company_id == company_id, EmployeeProfile.user_id.in_(ids))
            .all()
        )
    }

    # Ciclos da empresa -> ano, e os 3 anos mais recentes a exibir.
    ciclos = db.query(EvaluationCycle).filter(EvaluationCycle.company_id == company_id).all()
    ciclo_ano = {c.id: _extrair_ano(c.name) for c in ciclos}
    anos = sorted({a for a in ciclo_ano.values() if a is not None})
    anos = anos[-3:] if anos else []

    avaliacoes = (
        db.query(Evaluation)
        .filter(
            Evaluation.company_id == company_id,
            Evaluation.collaborator_id.in_(ids),
            Evaluation.phase == EvaluationPhase.VALIDADA,
            Evaluation.final_score.isnot(None),
        )
        .all()
    )
    scores_por_user: dict[int, dict[str, float]] = {}
    for ev in avaliacoes:
        ano = ciclo_ano.get(ev.cycle_id)
        if ano is None:
            continue
        scores_por_user.setdefault(ev.collaborator_id, {})[str(ano)] = ev.final_score

    # Processo disciplinar ativo (não arquivado) -> situação "preocupante".
    disc_ids = {
        r[0]
        for r in db.query(DisciplinaryProcess.accused_id)
        .filter(
            DisciplinaryProcess.company_id == company_id,
            DisciplinaryProcess.accused_id.in_(ids),
            DisciplinaryProcess.phase != DisciplinaryPhase.ARQUIVADO,
        )
        .all()
    }

    # Licença aprovada (férias / maternidade / doença) -> situação "licença".
    leave_ids = {
        r[0]
        for r in db.query(LeaveRequest.collaborator_id)
        .filter(
            LeaveRequest.company_id == company_id,
            LeaveRequest.collaborator_id.in_(ids),
            LeaveRequest.leave_type != LeaveType.FALTA,
            LeaveRequest.status.in_((LeaveStatus.APROVADA, LeaveStatus.JUSTIFICADA)),
        )
        .all()
    }

    # Nome curto da empresa (primeira palavra).
    empresa = db.query(Company).filter(Company.id == company_id).first()
    company_short = None
    if empresa and empresa.name:
        tokens = [t for t in empresa.name.split() if re.search(r"[A-Za-zÀ-ÿ]", t)]
        if tokens:
            company_short = tokens[0].rstrip(",;.")

    linhas = []
    for u in usuarios:
        p = perfis.get(u.id)
        scores = {str(a): scores_por_user.get(u.id, {}).get(str(a)) for a in anos}
        linhas.append(
            CollaboratorRowOut(
                id=u.id,
                company_id=u.company_id,
                email=u.email,
                full_name=u.full_name,
                role=u.role,
                is_active=u.is_active,
                created_at=u.created_at,
                employee_number=p.employee_number if p else None,
                job_title=p.job_title if p else None,
                job_category=p.job_category if p else None,
                department=p.department if p else None,
                admission_year=str(p.admission_date.year) if p and p.admission_date else None,
                situation_tags=p.situation_tags if p else None,
                score_years=anos,
                scores=scores,
                has_disciplinary=u.id in disc_ids,
                has_leave=u.id in leave_ids,
                company_short=company_short,
            )
        )
    return linhas


def _get_company_user_or_404(db: Session, company_id: int, user_id: int) -> User:
    """
    Procura um utilizador pelo id MAS restrito à empresa indicada.
    Se não existir nessa empresa, devolve 404 — nunca revela que o id existe
    noutra empresa. Isto é parte do isolamento multi-tenant.
    """
    user = (
        db.query(User)
        .filter(User.id == user_id, User.company_id == company_id)
        .first()
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Colaborador não encontrado.",
        )
    return user


@router.post("", response_model=CollaboratorCreatedOut, status_code=status.HTTP_201_CREATED)
def create_collaborator(
    payload: CollaboratorCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    """
    Cria um colaborador na empresa do utilizador autenticado.
    Gera uma password temporária, devolvida uma única vez.
    """
    company_id = current_user.company_id

    # Controlo de perfis: o Capital Humano só pode criar colaboradores comuns.
    # Atribuir perfis privilegiados é competência do Admin da empresa.
    perfis_privilegiados = (
        UserRole.DIRECTOR, UserRole.CAPITAL_HUMANO, UserRole.COMISSAO_AVALIACAO,
        UserRole.ADMINISTRACAO, UserRole.ADMIN, UserRole.SUPERADMIN,
    )
    if payload.role in perfis_privilegiados and current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Apenas o Admin da empresa pode atribuir este perfil. O Capital Humano cria colaboradores.",
        )

    # Email único dentro da empresa.
    exists = (
        db.query(User)
        .filter(User.company_id == company_id, User.email == payload.email)
        .first()
    )
    if exists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe um colaborador com este email nesta empresa.",
        )

    temp_password = secrets.token_urlsafe(9)  # ~12 caracteres legíveis

    collaborator = User(
        company_id=company_id,
        email=payload.email,
        hashed_password=hash_password(temp_password),
        full_name=payload.full_name,
        role=payload.role,
        must_change_password=True,  # obriga a trocar no primeiro acesso
    )
    db.add(collaborator)
    db.commit()
    db.refresh(collaborator)

    # Atribui automaticamente o número de colaborador (sequencial, 4 dígitos).
    #
    # Dois pedidos de criação em simultâneo podem calcular o mesmo "maior + 1"
    # antes de qualquer um comitar (não há lock nem sequência dedicada em
    # SQLite/Postgres aqui). A UniqueConstraint (company_id, employee_number)
    # em EmployeeProfile apanha a colisão no INSERT — em vez de a engolir em
    # silêncio, repetimos com o número seguinte, mantendo o padrão sequencial
    # (nunca aleatório) pedido para este campo.
    from app.models.employee_profile import EmployeeProfile

    for tentativa in range(5):
        existentes = (
            db.query(EmployeeProfile.employee_number)
            .filter(
                EmployeeProfile.company_id == company_id,
                EmployeeProfile.employee_number.isnot(None),
            )
            .all()
        )
        maior = 0
        for (num,) in existentes:
            try:
                n = int(str(num).lstrip("0") or "0")
                if n > maior:
                    maior = n
            except (ValueError, TypeError):
                continue
        novo_numero = f"{maior + 1 + tentativa:04d}"

        perfil = (
            db.query(EmployeeProfile)
            .filter(EmployeeProfile.user_id == collaborator.id)
            .first()
        )
        if perfil is None:
            perfil = EmployeeProfile(
                company_id=company_id,
                user_id=collaborator.id,
                employee_number=novo_numero,
                # Sexo escolhido no passo "Conta" do cadastro; o passo "Ficha"
                # volta a gravá-lo com o resto dos dados profissionais.
                gender=payload.gender,
            )
            db.add(perfil)
        else:
            perfil.employee_number = novo_numero

        try:
            db.commit()
            break
        except IntegrityError as e:
            db.rollback()
            log.warning(
                "Colisão no número de colaborador (tentativa %d/5) para company_id=%s: %s",
                tentativa + 1, company_id, e,
            )
    else:
        log.error(
            "Não foi possível atribuir número de colaborador após 5 tentativas (company_id=%s, user_id=%s).",
            company_id, collaborator.id,
        )


        # Envia o email de boas-vindas com as credenciais (email centralizado da KAMBA).
    # Se o email não estiver configurado, o cadastro decorre à mesma.
    try:
        from app.services.email_service import email_boas_vindas
        from app.models.company import Company
        empresa = db.query(Company).filter(Company.id == company_id).first()
        email_boas_vindas(
            nome=collaborator.full_name,
            email=collaborator.email,
            senha_temporaria=temp_password,
            empresa=empresa.name if empresa else "",
        )
    except Exception as e:
        print(f"[EMAIL] Não foi possível enviar boas-vindas: {e}")
    
    
    return CollaboratorCreatedOut(
        id=collaborator.id,
        full_name=collaborator.full_name,
        email=collaborator.email,
        role=collaborator.role.value if hasattr(collaborator.role, "value") else str(collaborator.role),
        collaborator=CollaboratorOut.model_validate(collaborator),
        temporary_password=temp_password,
    )


@router.get("", response_model=list[CollaboratorRowOut])
def list_collaborators(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
    role: UserRole | None = Query(default=None, description="Filtrar por perfil"),
    is_active: bool | None = Query(default=None, description="Filtrar por estado"),
    search: str | None = Query(default=None, description="Procurar por nome ou email"),
):
    """Lista os colaboradores da empresa do utilizador, com filtros opcionais."""
    query = db.query(User).filter(User.company_id == current_user.company_id)

    if role is not None:
        query = query.filter(User.role == role)
    if is_active is not None:
        query = query.filter(User.is_active == is_active)
    if search:
        like = f"%{search}%"
        query = query.filter(
            (User.full_name.ilike(like)) | (User.email.ilike(like))
        )

    usuarios = query.order_by(User.full_name).all()
    return _enriquecer_colaboradores(db, current_user, usuarios)


@router.get("/my-direction", response_model=list[CollaboratorRowOut])
def list_my_direction_collaborators(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.DIRECTOR)),
):
    """
    Lista os colaboradores da direção que o director gere.

    A direção do director vem da sua ficha (profile.department). Devolve os
    utilizadores da mesma empresa cuja ficha tem essa mesma direção,
    excluindo perfis de gestão (outros directores/CH/administração) — a equipa
    que o director avalia e acompanha.
    """
    from app.models.employee_profile import EmployeeProfile

    company_id = current_user.company_id
    perfil_director = (
        db.query(EmployeeProfile)
        .filter(EmployeeProfile.user_id == current_user.id)
        .first()
    )
    direcao = perfil_director.department if perfil_director else None
    if not direcao:
        # Sem direção atribuída na ficha: devolve vazio.
        return []

    excluidos = (
        UserRole.DIRECTOR, UserRole.CAPITAL_HUMANO,
        UserRole.COMISSAO_AVALIACAO, UserRole.ADMINISTRACAO,
        UserRole.ADMIN, UserRole.SUPERADMIN,
    )
    usuarios = (
        db.query(User)
        .join(EmployeeProfile, EmployeeProfile.user_id == User.id)
        .filter(
            User.company_id == company_id,
            EmployeeProfile.department == direcao,
            User.role.notin_(excluidos),
        )
        .order_by(User.full_name)
        .all()
    )
    return _enriquecer_colaboradores(db, current_user, usuarios)


@router.get("/{collaborator_id}", response_model=CollaboratorOut)
def get_collaborator(
    collaborator_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    """Devolve um colaborador específico da empresa do utilizador."""
    return _get_company_user_or_404(db, current_user.company_id, collaborator_id)


@router.patch("/{collaborator_id}", response_model=CollaboratorOut)
def update_collaborator(
    collaborator_id: int,
    payload: CollaboratorUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    """Atualiza os dados de um colaborador da empresa do utilizador."""
    collaborator = _get_company_user_or_404(
        db, current_user.company_id, collaborator_id
    )

    data = payload.model_dump(exclude_unset=True)
    if "email" in data:
        new_email = data["email"]
        if new_email is None:
            raise HTTPException(status_code=422, detail="O email não pode ser vazio.")
        new_email = str(new_email).strip().lower()
        email_exists = (
            db.query(User)
            .filter(
                User.company_id == current_user.company_id,
                func.lower(User.email) == new_email,
                User.id != collaborator.id,
            )
            .first()
        )
        if email_exists is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Já existe um colaborador com este email nesta empresa.",
            )
        data["email"] = new_email

    for field, value in data.items():
        setattr(collaborator, field, value)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe um colaborador com este email nesta empresa.",
        )
    db.refresh(collaborator)
    return collaborator


@router.post("/{collaborator_id}/deactivate", response_model=CollaboratorOut)
def deactivate_collaborator(
    collaborator_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    """
    Desativa um colaborador (não apaga — num sistema com histórico legal,
    desativa-se, preservando o registo). Impede desativar a própria conta.
    """
    if collaborator_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não pode desativar a sua própria conta.",
        )
    collaborator = _get_company_user_or_404(
        db, current_user.company_id, collaborator_id
    )
    collaborator.is_active = False
    db.commit()
    db.refresh(collaborator)
    return collaborator


@router.post("/{collaborator_id}/reactivate", response_model=CollaboratorOut)
def reactivate_collaborator(
    collaborator_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    """Reativa um colaborador previamente desativado."""
    collaborator = _get_company_user_or_404(
        db, current_user.company_id, collaborator_id
    )
    collaborator.is_active = True
    db.commit()
    db.refresh(collaborator)
    return collaborator


@router.post("/{collaborator_id}/reset-password", response_model=PasswordResetOut)
def reset_password(
    collaborator_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    """
    Gera uma nova password temporária para um colaborador da empresa.

    Serve para o caso em que o email de boas-vindas não chegou (SMTP não
    configurado, email inválido) ou o colaborador perdeu a password inicial.
    A nova password é devolvida uma única vez na resposta — o gestor entrega-a
    em mãos — e o colaborador é obrigado a trocá-la no primeiro acesso
    (must_change_password=True).
    """
    collaborator = _get_company_user_or_404(
        db, current_user.company_id, collaborator_id
    )
    if collaborator.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não pode redefinir a sua própria password por aqui. Use a troca de password.",
        )
    if not collaborator.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível redefinir a password de uma conta inactiva.",
        )

    temp_password = secrets.token_urlsafe(9)  # ~12 caracteres legíveis

    collaborator.hashed_password = hash_password(temp_password)
    collaborator.must_change_password = True
    db.commit()
    db.refresh(collaborator)

    # Tenta reenviar o email de boas-vindas; se falhar, o gestor entrega a
    # password em mãos (a resposta da API continua a trazê-la).
    try:
        from app.services.email_service import email_boas_vindas
        from app.models.company import Company
        empresa = db.query(Company).filter(Company.id == collaborator.company_id).first()
        email_boas_vindas(
            nome=collaborator.full_name,
            email=collaborator.email,
            senha_temporaria=temp_password,
            empresa=empresa.name if empresa else "",
        )
    except Exception as e:
        print(f"[EMAIL] Não foi possível reenviar boas-vindas: {e}")

    return PasswordResetOut(
        id=collaborator.id,
        full_name=collaborator.full_name,
        email=collaborator.email,
        temporary_password=temp_password,
    )


# ---------- Documentos anexados do colaborador (contrato secção 2) ----------

from fastapi import UploadFile, File, Form
from app.models.collaborator_document import CollaboratorDocument
from app.services.cloudinary_upload import upload_file as _cloud_upload

_DOC_TYPES = ("bi", "contrato_assinado", "certificado_habilitacoes", "outro")


def _doc_out(d: CollaboratorDocument) -> dict:
    return {
        "id": d.id,
        "filename": d.filename,
        "doc_type": d.doc_type,
        "file_url": d.file_url,
        "uploaded_at": d.uploaded_at.isoformat(),
    }
@router.get("/me/documents")
def my_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """O próprio colaborador vê os seus documentos (BI, contrato, certificados)."""
    rows = (
        db.query(CollaboratorDocument)
        .filter(
            CollaboratorDocument.company_id == current_user.company_id,
            CollaboratorDocument.collaborator_id == current_user.id,
        )
        .order_by(CollaboratorDocument.id.desc())
        .all()
    )
    return [_doc_out(d) for d in rows]


@router.post("/{collaborator_id}/documents", status_code=201)
async def upload_collaborator_document(
    collaborator_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CAPITAL_HUMANO, UserRole.ADMINISTRACAO, UserRole.ADMIN)),
    file: UploadFile = File(...),
    doc_type: str = Form(...),
):
    """O Capital Humano anexa um documento (BI, contrato, certificado) a um colaborador."""
    if doc_type not in _DOC_TYPES:
        raise HTTPException(status_code=422, detail="Tipo de documento inválido.")
    conteudo = await file.read()
    url = _cloud_upload(conteudo, file.filename, folder="kamba/colaboradores")
    doc = CollaboratorDocument(
        company_id=current_user.company_id,
        collaborator_id=collaborator_id,
        filename=file.filename,
        doc_type=doc_type,
        file_url=url,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return _doc_out(doc)


@router.get("/{collaborator_id}/documents")
def list_collaborator_documents(
    collaborator_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CAPITAL_HUMANO, UserRole.ADMINISTRACAO, UserRole.ADMIN)),
):
    """Lista os documentos anexados a um colaborador."""
    rows = (
        db.query(CollaboratorDocument)
        .filter(
            CollaboratorDocument.company_id == current_user.company_id,
            CollaboratorDocument.collaborator_id == collaborator_id,
        )
        .order_by(CollaboratorDocument.id.desc())
        .all()
    )
    return [_doc_out(d) for d in rows]


@router.delete("/{collaborator_id}/documents/{doc_id}")
def delete_collaborator_document(
    collaborator_id: int,
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CAPITAL_HUMANO, UserRole.ADMINISTRACAO, UserRole.ADMIN)),
):
    """Remove um documento anexado."""
    d = (
        db.query(CollaboratorDocument)
        .filter(
            CollaboratorDocument.id == doc_id,
            CollaboratorDocument.company_id == current_user.company_id,
        )
        .first()
    )
    if not d:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    db.delete(d)
    db.commit()
    return {"detail": "Documento removido."}


# ---------- Alterar o perfil (role) de um colaborador ----------

from pydantic import BaseModel as _BaseModel


class RoleUpdate(_BaseModel):
    role: UserRole


@router.patch("/{collaborator_id}/role", response_model=CollaboratorOut)
def change_role(
    collaborator_id: int,
    payload: RoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    """
    Altera o perfil (role) de um colaborador. Reservado a Capital Humano e
    Administração. Não permite alterar o próprio perfil (evita despromoção
    acidental do próprio gestor).
    """
    if collaborator_id == current_user.id:
        raise HTTPException(
            status_code=400,
            detail="Não pode alterar o seu próprio perfil.",
        )
    collaborator = (
        db.query(User)
        .filter(User.id == collaborator_id, User.company_id == current_user.company_id)
        .first()
    )
    if collaborator is None:
        raise HTTPException(status_code=404, detail="Colaborador não encontrado.")

    collaborator.role = payload.role
    db.commit()
    db.refresh(collaborator)

    # Notifica o colaborador da mudança de perfil.
    try:
        from app.services.notifications import notify
        notify(
            db, company_id=current_user.company_id, user_id=collaborator.id,
            title="Perfil de acesso atualizado",
            message=f"O seu perfil foi alterado para {payload.role.value}.",
            category="conta", link="/",
        )
        db.commit()
    except Exception:
        pass

    return CollaboratorOut.model_validate(collaborator)


# ---------- CV em PDF (Modelo Europeu de Curriculum Vitae) ----------

MESES_PT = (
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
)


@router.get("/{collaborator_id}/cv-pdf")
def gerar_cv_pdf(
    collaborator_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    """Gera o Curriculum Vitae do colaborador no layout do Modelo Europeu."""
    from io import BytesIO
    from datetime import date
    from html import escape
    from fastapi.responses import StreamingResponse
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
    from reportlab.platypus import (
        BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table, TableStyle,
        Flowable, Image as ReportImage,
    )
    from app.models.company import Company
    from app.models.employee_profile import EmployeeProfile
    from app.services.cloudinary_upload import fetch_image

    user = (
        db.query(User)
        .filter(User.id == collaborator_id, User.company_id == current_user.company_id)
        .first()
    )
    if user is None:
        raise HTTPException(status_code=404, detail="Colaborador não encontrado.")

    profile = (
        db.query(EmployeeProfile)
        .filter(EmployeeProfile.user_id == collaborator_id)
        .first()
    )
    empresa = (
        db.query(Company)
        .filter(Company.id == current_user.company_id)
        .first()
    )

    # --- Geometria do formulário (medidas do original em A4) ---
    marg_esq, marg_dir = 1.3 * cm, 1.6 * cm
    larg_rotulo, vao, larg_valor = 4.9 * cm, 0.8 * cm, 12.4 * cm
    larg_total = larg_rotulo + vao + larg_valor

    est_rotulo = ParagraphStyle(
        "Rotulo", fontName="Helvetica", fontSize=10, leading=11.5,
        alignment=TA_RIGHT, spaceAfter=0,
    )
    est_valor = ParagraphStyle(
        "Valor", fontName="Helvetica", fontSize=10, leading=11.5,
        alignment=TA_LEFT, spaceAfter=0,
    )
    est_valor_nome = ParagraphStyle(
        "ValorNome", parent=est_valor, fontName="Helvetica-Bold", fontSize=11,
    )
    est_secao = ParagraphStyle(
        "Secao", fontName="Helvetica-Bold", fontSize=9.5, leading=12.5,
        alignment=TA_LEFT, spaceAfter=0,
    )
    est_sub = ParagraphStyle(
        "SubSecao", fontName="Helvetica-BoldOblique", fontSize=11, leading=13,
        alignment=TA_CENTER, spaceAfter=0,
    )
    est_livre = ParagraphStyle(
        "Livre", fontName="Helvetica", fontSize=10, leading=11.5, alignment=TA_LEFT,
    )
    est_idioma_cab = ParagraphStyle(
        "IdiomaCab", fontName="Helvetica-Bold", fontSize=10, leading=12, alignment=TA_LEFT,
    )

    def para(texto, estilo=est_valor):
        limpo = (texto or "").strip()
        return Paragraph(escape(limpo or "—").replace("\n", "<br/>"), estilo)

    def cabecalho_secao(titulo):
        # Como no original: primeira letra maior, restante em corpo menor.
        return Paragraph(
            f'<font size="12">{escape(titulo[0])}</font>'
            f'<font size="9.5">{escape(titulo[1:])}</font>',
            est_secao,
        )

    def linha(rotulo, valor, bullets=True, estilo_valor=est_valor):
        if bullets:
            celula = Paragraph(f"<b>•</b> {escape(rotulo)}", est_rotulo)
        else:
            celula = para(rotulo, est_rotulo)
        return [celula, para(valor, estilo_valor)]

    def intervalo(inicio, fim):
        inicio, fim = (str(inicio).strip() if inicio else ""), (str(fim).strip() if fim else "")
        if inicio and fim:
            return f"[{inicio} – {fim}]"
        if inicio:
            return f"[{inicio} – até à data]"
        return f"[{fim}]" if fim else None

    def data_extenso(valor):
        if valor is None:
            return None
        if valor.month == 1:
            return str(valor.year)
        return f"{MESES_PT[valor.month - 1]} de {valor.year}"

    def ano_de(valor):
        """Ano a partir de uma data ou de uma string ISO (colunas JSON)."""
        if not valor:
            return None
        if hasattr(valor, "year"):
            return str(valor.year)
        try:
            return str(date.fromisoformat(str(valor)[:10]).year)
        except ValueError:
            return str(valor)

    class TituloEspacado(Flowable):
        """Título com espaçamento entre letras, como no formulário original."""

        def __init__(self, texto, largura):
            super().__init__()
            self.texto, self.largura, self.altura = texto, largura, 1.7 * cm

        def wrap(self, avail_width, avail_height):
            self.largura = min(self.largura, avail_width)
            return self.largura, self.altura

        def draw(self):
            c, espaco = self.canv, 1.5
            primeiro, resto = self.texto[0], self.texto[1:]
            c.setFont("Helvetica-Bold", 14)
            larg_1 = c.stringWidth(primeiro, "Helvetica-Bold", 14) + espaco
            c.setFont("Helvetica-Bold", 11)
            larg_2 = c.stringWidth(resto, "Helvetica-Bold", 11) + espaco * max(len(resto) - 1, 0)
            x, y = (self.largura - larg_1 - larg_2) / 2, self.altura - 14
            c.setFont("Helvetica-Bold", 14)
            c.drawString(x, y, primeiro)
            texto = c.beginText(x + larg_1, y + 2.3)
            texto.setFont("Helvetica-Bold", 11)
            texto.setCharSpace(espaco)
            texto.textOut(resto)
            c.drawText(texto)

    def tabela(linhas, larguras=None):
        larguras = larguras or [larg_rotulo, larg_valor]
        estilo = [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ]
        if len(larguras) == 2:
            estilo.append(("LEFTPADDING", (1, 0), (1, -1), vao))
        t = Table(linhas, colWidths=larguras, splitByRow=1, splitInRow=1, hAlign="LEFT")
        t.setStyle(TableStyle(estilo))
        return t

    def bloco_livre(texto, largura=larg_rotulo):
        """Secções de texto livre (aptidões), escritas na coluna da esquerda."""
        return tabela([[para(texto, est_livre)]], [largura])

    def sub_titulo(texto):
        # Centrado na coluna da esquerda, como no formulário original.
        t = Table([[para(texto, est_sub)]], colWidths=[larg_rotulo + vao], hAlign="LEFT")
        t.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        return t

    elementos = []

    # --- Cabeçalho: título (à esquerda) e fotografia (à direita) ---
    foto = None
    if profile and profile.photo_url:
        dados_foto = fetch_image(profile.photo_url)
        if dados_foto:
            try:
                foto = ReportImage(BytesIO(dados_foto), width=3.2 * cm, height=4.3 * cm,
                                   kind="proportional")
            except Exception:
                foto = None

    if foto is not None:
        titulo = TituloEspacado("CURRÍCULO VITAE", larg_total - 4 * cm)
        cabecalho = Table([[titulo, foto]], colWidths=[larg_total - 4 * cm, 4 * cm], hAlign="LEFT")
        cabecalho.setStyle(TableStyle([
            ("VALIGN", (0, 0), (0, 0), "MIDDLE"),
            ("VALIGN", (1, 0), (1, 0), "TOP"),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
    else:
        cabecalho = TituloEspacado("CURRÍCULO VITAE", larg_total)
    elementos += [cabecalho, Spacer(1, 10)]

    # --- INFORMAÇÃO PESSOAL ---
    pessoais = [linha("Nome", user.full_name, bullets=False, estilo_valor=est_valor_nome)]
    if profile:
        if profile.address:
            pessoais.append(linha("Morada", profile.address, bullets=False))
        if profile.phone:
            pessoais.append(linha("Telefone", profile.phone, bullets=False))
    if user.email:
        pessoais.append(linha("Correio electrónico", user.email, bullets=False))
    if profile and profile.birth_date:
        pessoais.append(linha("Data de nascimento",
                              profile.birth_date.strftime("%d/%m/%Y"), bullets=False))
    if profile and profile.nationality:
        pessoais.append(linha("Nacionalidade", profile.nationality, bullets=False))
    elementos += [cabecalho_secao("INFORMAÇÃO PESSOAL"), tabela(pessoais)]

    # --- EXPERIÊNCIA PROFISSIONAL ---
    experiencias = list(profile.experience or []) if profile else []
    empregador_atual = empresa.name if empresa else None
    if profile and (profile.job_title or empregador_atual):
        if not any((x.get("onde") or "").strip().lower() == (empregador_atual or "").strip().lower()
                   for x in experiencias):
            experiencias.insert(0, {
                "onde": empregador_atual,
                "funcao": profile.job_title,
                "datas": intervalo(data_extenso(profile.admission_date), None),
            })
    if experiencias:
        linhas = []
        for x in experiencias:
            if not isinstance(x, dict):
                continue
            bloco = []
            datas = x.get("datas") or intervalo(x.get("ano_inicio"), x.get("ano_fim"))
            if datas:
                bloco.append(linha("Datas (de – até)", datas))
            if x.get("onde"):
                bloco.append(linha("Nome e endereço do empregador", x["onde"]))
            if x.get("sector"):
                bloco.append(linha("Tipo de empresa ou sector", x["sector"]))
            if x.get("funcao"):
                bloco.append(linha("Função ou cargo ocupado", x["funcao"]))
            if x.get("actividades"):
                bloco.append(linha("Principais actividades e responsabilidades", x["actividades"]))
            if bloco:
                linhas += bloco + [["", ""]]
        elementos += [
            Spacer(1, 9), cabecalho_secao("EXPERIÊNCIA PROFISSIONAL"),
            sub_titulo("Cargos e Funções"), tabela(linhas),
        ]

    # --- FORMAÇÃO ACADÉMICA E PROFISSIONAL MAIS RELEVANTE ---
    formacoes = [f for f in (profile.education or []) if isinstance(f, dict)] if profile else []
    if not formacoes and profile and (profile.university or profile.course or profile.habilitacoes):
        formacoes = [{
            "nivel": profile.habilitacoes, "instituicao": profile.university,
            "curso": profile.course, "areas": None, "pais": None,
        }]
    if formacoes:
        linhas = []
        for f in formacoes:
            bloco = []
            datas = intervalo(f.get("ano_inicio"), f.get("ano_fim"))
            if datas:
                bloco.append(linha("Datas (de – até)", datas))
            instituicao = f.get("instituicao") or (profile.university if profile else None)
            if instituicao and f.get("pais"):
                instituicao = f"{instituicao} — {f['pais']}"
            if instituicao:
                bloco.append(linha("Nome e tipo de Organização de ensino ou formação", instituicao))
            if f.get("areas"):
                bloco.append(linha("Principais disciplinas/competências profissionais", f["areas"]))
            elif f.get("curso"):
                bloco.append(linha("Principais disciplinas/competências profissionais", f["curso"]))
            if f.get("nivel"):
                bloco.append(linha("Designação da qualificação atribuída", f["nivel"]))
            if bloco:
                linhas += bloco + [["", ""]]
        elementos += [
            Spacer(1, 9), cabecalho_secao("FORMAÇÃO ACADÉMICA E PROFISSIONAL MAIS RELEVANTE"),
            tabela(linhas),
        ]

    # --- CURSOS E FORMAÇÃO COMPLEMENTARES ---
    cursos = []
    for c in (profile.certifications or []) if profile else []:
        if not isinstance(c, dict):
            continue
        if c.get("data"):
            quando = ano_de(c["data"])
        elif c.get("validade"):
            quando = f"válido até {ano_de(c['validade'])}"
        else:
            quando = None
        partes = [p for p in [quando, c.get("nome"), c.get("instituicao")] if p]
        if partes:
            cursos.append(" – ".join(str(p) for p in partes))
    if cursos:
        elementos += [
            Spacer(1, 9), cabecalho_secao("CURSOS E FORMAÇÃO COMPLEMENTARES"),
            tabela([["", para("\n".join(cursos), est_livre)]]),
        ]

    # --- IDIOMAS ---
    idiomas = [
        i for i in (profile.languages or []) if isinstance(i, dict) and i.get("nome")
    ] if profile else []
    if idiomas:
        linhas = [[
            para("Idioma", est_idioma_cab), para("Fala", est_idioma_cab),
            para("Escreve", est_idioma_cab), para("Lê", est_idioma_cab),
        ]]
        for i in idiomas:
            linhas.append([
                para(i.get("nome")), para(i.get("fala")), para(i.get("escreve")), para(i.get("le")),
            ])
        elementos += [
            Spacer(1, 9), cabecalho_secao("IDIOMAS"),
            tabela(linhas, [6.5 * cm, 3.9 * cm, 3.9 * cm, 3.8 * cm]),
        ]

    # --- APTIDÕES E COMPETÊNCIAS (texto livre na coluna da esquerda) ---
    if profile and profile.social_skills:
        elementos += [Spacer(1, 9), cabecalho_secao("APTIDÕES E COMPETÊNCIAS SOCIAIS"),
                      bloco_livre(profile.social_skills)]
    if profile and profile.technical_skills:
        elementos += [Spacer(1, 9), cabecalho_secao("APTIDÕES E COMPETÊNCIAS TÉCNICAS"),
                      bloco_livre(profile.technical_skills)]

    # --- PERFIL ---
    if profile and profile.cv:
        elementos += [Spacer(1, 9), cabecalho_secao("PERFIL"),
                      tabela([["", para(profile.cv, est_livre)]])]

    # --- Local e data ---
    hoje = date.today()
    local = (profile.workplace if profile else None) or ""
    elementos += [
        Spacer(1, 14),
        para(f"{local} {hoje.day:02d} de {MESES_PT[hoje.month - 1]} de {hoje.year}".strip(), est_livre),
    ]

    buf = BytesIO()
    doc = BaseDocTemplate(
        buf, pagesize=A4, leftMargin=marg_esq, rightMargin=marg_dir,
        topMargin=2 * cm, bottomMargin=1.5 * cm,
        title=f"Curriculum Vitae — {user.full_name or 'Colaborador'}",
        author=user.full_name or None,
    )
    # Frame sem padding: as margens passam a ser as medidas reais do formulário.
    moldura = Frame(
        marg_esq, 1.5 * cm, A4[0] - marg_esq - marg_dir, A4[1] - 2 * cm - 1.5 * cm,
        id="cv", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
    )
    doc.addPageTemplates([PageTemplate(id="cv", frames=[moldura])])
    doc.build(elementos)
    buf.seek(0)

    filename = f"CV_{(user.full_name or 'colaborador').replace(' ', '_')}.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )



# ---------- Ficha profissional completa em PDF ----------

@router.get("/{collaborator_id}/ficha-pdf")
def gerar_ficha_pdf(
    collaborator_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Gera a Ficha Profissional completa do colaborador em PDF.

    Documento organizado e pronto a imprimir: identificação e vínculo,
    formação académica, experiência profissional, cursos e certificações e o
    conteúdo de CV / notas. Acede quem gere pessoas (CH/Administração/Admin)
    ou o próprio colaborador (a sua própria ficha).
    """
    from io import BytesIO
    from datetime import date
    from html import escape
    from fastapi.responses import StreamingResponse
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib.colors import HexColor
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as ReportImage
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from app.models.company import Company
    from app.models.employee_profile import EmployeeProfile
    from app.services.cloudinary_upload import fetch_image

    # Permissão: gestão de pessoas ou o próprio colaborador.
    if current_user.id != collaborator_id and current_user.role not in MANAGE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Não tem permissão para ver a ficha deste colaborador.",
        )

    user = (
        db.query(User)
        .filter(User.id == collaborator_id, User.company_id == current_user.company_id)
        .first()
    )
    if user is None:
        raise HTTPException(status_code=404, detail="Colaborador não encontrado.")

    profile = (
        db.query(EmployeeProfile)
        .filter(EmployeeProfile.user_id == collaborator_id)
        .first()
    )
    empresa = db.query(Company).filter(Company.id == current_user.company_id).first()

    def limpar(texto) -> str:
        return escape(str(texto)) if texto is not None else ""

    def fmt_data(v) -> str:
        if not v:
            return "—"
        if hasattr(v, "strftime"):
            try:
                return v.strftime("%d/%m/%Y")
            except Exception:
                pass
        return str(v)

    def rotulo_vinculo(v) -> str:
        if not v:
            return "—"
        mapa = {
            "efetivo": "Por tempo indeterminado",
            "termo_certo": "Tempo determinado",
            "termo_incerto": "Tempo determinado",
            "estagio": "Estágio",
            "prestacao_servicos": "Prestação de serviços",
        }
        return mapa.get(str(v), str(v))

    def get_(campo, padrao="—"):
        if profile is None or getattr(profile, campo, None) is None:
            return padrao
        return limpar(getattr(profile, campo))

    def foto_perfil():
        if not profile or not profile.photo_url:
            return None
        dados = fetch_image(profile.photo_url)
        if not dados:
            return None
        try:
            image = ReportImage(BytesIO(dados), width=3.2 * cm, height=3.2 * cm, kind="proportional")
            image.hAlign = "CENTER"
            return image
        except Exception:
            return None

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
                            topMargin=1.8 * cm, bottomMargin=1.8 * cm)
    styles = getSampleStyleSheet()

    titulo_estilo = ParagraphStyle("Titulo", parent=styles["Title"], fontSize=19,
                                   textColor=HexColor("#14532d"), spaceAfter=1)
    sub_estilo = ParagraphStyle("Sub", parent=styles["Normal"], fontSize=11.5,
                                textColor=HexColor("#1e3a5f"), spaceAfter=2)
    cab_estilo = ParagraphStyle("Cab", parent=styles["Normal"], fontSize=9,
                                textColor=HexColor("#9aa7b0"), alignment=TA_CENTER, spaceAfter=0)
    sec_estilo = ParagraphStyle("Sec", parent=styles["Heading2"], fontSize=12.5,
                                textColor=HexColor("#14532d"), spaceBefore=14, spaceAfter=6)
    rot_estilo = ParagraphStyle("Rot", parent=styles["Normal"], fontSize=9,
                                textColor=HexColor("#666666"))
    corpo_estilo = ParagraphStyle("Corpo", parent=styles["Normal"], fontSize=10.5, leading=14.5)
    pe_estilo = ParagraphStyle("Pe", parent=styles["Normal"], fontSize=9,
                               textColor=HexColor("#9aa7b0"), spaceBefore=16, alignment=TA_CENTER)

    elems = []

    # Cabeçalho do documento.
    elems.append(Paragraph("Ficha Profissional", titulo_estilo))
    foto = foto_perfil()
    if foto is not None:
        elems.append(foto)
        elems.append(Spacer(1, 4))
    else:
        elems.append(Paragraph(limpar(user.full_name) or "Colaborador", sub_estilo))
    elems.append(Paragraph(empresa.name if empresa and empresa.name else "KAMBA", cab_estilo))
    elems.append(Paragraph(f"Impresso em {date.today().strftime('%d/%m/%Y')}", cab_estilo))
    elems.append(Spacer(1, 6))

    # 1. Identificação e vínculo.
    elems.append(Paragraph("1. Identificação e vínculo", sec_estilo))
    dados = [
        ("Nome completo", limpar(user.full_name) or "—"),
        ("Email", limpar(user.email) or "—"),
        ("N.º de colaborador", get_("employee_number")),
        ("Data de admissão", fmt_data(profile.admission_date) if profile else "—"),
        ("Vínculo", rotulo_vinculo(profile.contract_type) if profile else "—"),
        ("Término do contrato", fmt_data(profile.contract_end_date) if profile else "—"),
        ("Categoria", get_("job_category")),
        ("Cargo", get_("job_title")),
        ("Direção", get_("department")),
        ("Local de trabalho", get_("workplace")),
        ("Horário", get_("work_schedule")),
        ("Nacionalidade", get_("nationality")),
        ("Habilitações literárias", get_("habilitacoes")),
        ("Universidade", get_("university")),
        ("Curso", get_("course")),
    ]
    t = Table(
        [[Paragraph(r, rot_estilo), Paragraph(v, corpo_estilo)] for r, v in dados],
        colWidths=[5.2 * cm, 10.8 * cm],
    )
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, HexColor("#e5e7eb")),
    ]))
    elems.append(t)

    def bloco_educacao():
        if not (profile and profile.education and isinstance(profile.education, list)):
            return
        elems.append(Paragraph("2. Formação académica", sec_estilo))
        for e in profile.education:
            if not isinstance(e, dict):
                continue
            titulo = limpar(e.get("curso") or e.get("nivel") or "Formação")
            linha = f"<b>{titulo}</b>"
            if e.get("nivel") and e.get("curso"):
                linha += f" &nbsp;·&nbsp; {limpar(str(e['nivel']))}"
            detalhes = []
            if e.get("instituicao"):
                detalhes.append(limpar(str(e["instituicao"])))
            periodo = []
            if e.get("ano_inicio"):
                periodo.append(str(e["ano_inicio"]))
            if e.get("ano_fim"):
                periodo.append(str(e["ano_fim"]))
            if periodo:
                detalhes.append("(" + " – ".join(periodo) + ")")
            if e.get("pais"):
                detalhes.append(limpar(str(e["pais"])))
            if detalhes:
                linha += "<br/><font size='9' color='#666666'>" + " &nbsp;·&nbsp; ".join(detalhes) + "</font>"
            if e.get("areas"):
                linha += f"<br/><font size='9' color='#333333'>Áreas: {limpar(str(e['areas']))}</font>"
            elems.append(Paragraph(linha, corpo_estilo))
            elems.append(Spacer(1, 5))

    def bloco_experiencia():
        if not (profile and profile.experience and isinstance(profile.experience, list) and len(profile.experience) > 0):
            return
        elems.append(Paragraph("3. Experiência profissional", sec_estilo))
        for x in profile.experience:
            if not isinstance(x, dict):
                continue
            partes = []
            if x.get("onde"):
                partes.append(f"<b>{limpar(str(x['onde']))}</b>")
            if x.get("funcao"):
                partes.append(limpar(str(x["funcao"])))
            periodo = []
            if x.get("ano_inicio"):
                periodo.append(str(x["ano_inicio"]))
            if x.get("ano_fim"):
                periodo.append(str(x["ano_fim"]))
            if periodo:
                partes.append("(" + " – ".join(periodo) + ")")
            elems.append(Paragraph(" &nbsp;·&nbsp; ".join([p for p in partes if p]) or "—", corpo_estilo))
            elems.append(Spacer(1, 5))

    def bloco_certificacoes():
        if not (profile and profile.certifications and isinstance(profile.certifications, list) and len(profile.certifications) > 0):
            return
        elems.append(Paragraph("4. Cursos e certificações", sec_estilo))
        for c in profile.certifications:
            if not isinstance(c, dict):
                continue
            linha = f"<b>{limpar(c.get('nome')) or 'Certificação'}</b>"
            detalhes = []
            if c.get("instituicao"):
                detalhes.append(limpar(str(c["instituicao"])))
            if c.get("data"):
                detalhes.append(str(c["data"]))
            if c.get("validade"):
                detalhes.append("válido até " + str(c["validade"]))
            if detalhes:
                linha += "<br/><font size='9' color='#666666'>" + " &nbsp;·&nbsp; ".join(detalhes) + "</font>"
            elems.append(Paragraph(linha, corpo_estilo))
            elems.append(Spacer(1, 5))

    def bloco_cv():
        if not (profile and profile.cv and str(profile.cv).strip()):
            return
        elems.append(Paragraph("5. CV e notas", sec_estilo))
        for linha_cv in str(profile.cv).split("\n"):
            elems.append(Paragraph(limpar(linha_cv) or "&nbsp;", corpo_estilo))

    bloco_educacao()
    bloco_experiencia()
    bloco_certificacoes()
    bloco_cv()

    if not dados and not profile:
        elems.append(Paragraph("Ficha sem dados preenchidos.", corpo_estilo))

    elems.append(Paragraph(f"Ficha gerada pela plataforma KAMBA — {empresa.name if empresa else ''}".strip(),
                           pe_estilo))

    doc.build(elems)
    buf.seek(0)

    filename = f"Ficha_{(user.full_name or 'colaborador').replace(' ', '_')}.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
