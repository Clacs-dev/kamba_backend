"""
Rotas de autenticação do KAMBA.
"""
import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import hash_password, verify_password, create_access_token
from app.models.company import Company
from app.models.user import User
from app.models.enums import UserRole
from app.schemas.auth import RegisterRequest, LoginRequest, TokenResponse, UserOut
from app.api.deps import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    """
    Regista uma nova empresa e o seu primeiro utilizador (Capital Humano).

    Este é o ponto de entrada de uma empresa cliente na plataforma. O
    utilizador criado tem o perfil CAPITAL_HUMANO, que é quem depois cadastra
    os restantes colaboradores de dentro do sistema.
    """
    # Cria a empresa (o tenant).
    company = Company(
        name=payload.company_name,
        vision=payload.vision,
        mission=payload.mission,
        values=payload.values,
        objectives=payload.objectives,
    )
    db.add(company)
    db.flush()  # obtém o company.id sem fechar a transacção

    # Verifica se já existe este email dentro desta empresa.
    exists = (
        db.query(User)
        .filter(User.company_id == company.id, User.email == payload.email)
        .first()
    )
    if exists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe um utilizador com este email nesta empresa.",
        )

    user = User(
        company_id=company.id,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=UserRole.ADMIN,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """
    Autentica um utilizador e devolve um token JWT.

    Nota: como o mesmo email pode existir em empresas diferentes, este login
    simples encontra o utilizador só pelo email. Enquanto cada email for único
    no conjunto de empresas de demonstração, funciona. Quando houver emails
    repetidos entre empresas, acrescentamos a identificação da empresa ao login.
    """
    user = db.query(User).filter(User.email == payload.email).first()
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou password incorrectos.",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Conta inactiva.",
        )

    token = create_access_token(
        subject=user.id,
        company_id=user.company_id,
        role=user.role.value,
    )
    return TokenResponse(access_token=token)


@router.post("/token", response_model=TokenResponse, include_in_schema=False)
def login_form(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """
    Login compatível com o formulário OAuth2 do Swagger (botão Authorize).
    O campo 'username' recebe o email. Serve apenas para testar no /docs;
    o frontend usa a rota /login com JSON.
    """
    user = db.query(User).filter(User.email == form_data.username).first()
    if user is None or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou password incorrectos.",
        )
    token = create_access_token(
        subject=user.id, company_id=user.company_id, role=user.role.value
    )
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserOut)
def me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Devolve o utilizador autenticado, incluindo o nome da sua empresa."""
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    return UserOut(
        id=current_user.id,
        company_id=current_user.company_id,
        company_name=company.name if company else None,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        is_active=current_user.is_active,
        must_change_password=current_user.must_change_password,
        created_at=current_user.created_at,
    )


# ---------- Troca de password ----------

from pydantic import BaseModel, Field as _Field, EmailStr


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = _Field(..., min_length=8, max_length=128)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordOut(BaseModel):
    detail: str
    temporary_password: str | None = None


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Troca a password do próprio utilizador. Verifica a password atual e
    limpa a marca 'must_change_password'.
    """
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="A password atual está incorreta.")
    if payload.new_password == payload.current_password:
        raise HTTPException(status_code=400, detail="A nova password deve ser diferente da atual.")

    current_user.hashed_password = hash_password(payload.new_password)
    current_user.must_change_password = False
    db.commit()
    return {"detail": "Password alterada com sucesso."}


@router.post("/forgot-password", response_model=ForgotPasswordOut)
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """
    Recuperação de acesso quando o utilizador esquece a password.

    Gera uma nova password temporária, marca must_change_password=True e tenta
    enviá-la por email. Como pode não haver email a receber (SMTP inativo ou
    colaborador sem caixa de correio), a nova password também é devolvida na
    resposta — quem está no atendimento entrega-a em mãos ao colaborador.

    Quando o email não pertence a nenhuma conta ativa, devolve uma mensagem
    genérica (igual para todos) para não revelar que emails existem.
    """
    user = db.query(User).filter(User.email == payload.email).first()
    if user is None or not user.is_active:
        return ForgotPasswordOut(
            detail="Se o email existir numa conta ativa, foi gerada uma nova password temporária."
        )

    temp_password = secrets.token_urlsafe(9)  # ~12 caracteres legíveis

    user.hashed_password = hash_password(temp_password)
    user.must_change_password = True
    db.commit()
    db.refresh(user)

    # Tenta reenviar o email de boas-vindas; se falhar, a password é entregue
    # em mãos a partir da resposta desta rota.
    try:
        from app.services.email_service import email_boas_vindas
        from app.models.company import Company
        empresa = db.query(Company).filter(Company.id == user.company_id).first()
        email_boas_vindas(
            nome=user.full_name,
            email=user.email,
            senha_temporaria=temp_password,
            empresa=empresa.name if empresa else "",
        )
    except Exception as e:
        print(f"[EMAIL] Não foi possível enviar recuperação: {e}")

    return ForgotPasswordOut(
        detail="Nova password temporária gerada. Altere-a no primeiro acesso.",
        temporary_password=temp_password,
    )
