"""
Rotas de autenticação do KAMBA.
"""
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
    company = Company(name=payload.company_name)
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
        role=UserRole.CAPITAL_HUMANO,
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
def me(current_user: User = Depends(get_current_user)):
    """Devolve o utilizador autenticado — útil para o frontend confirmar a sessão."""
    return current_user
