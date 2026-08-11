"""
Schemas Pydantic — o contrato de dados da API de autenticação.

Definem exactamente o que entra e o que sai de cada rota. O frontend usa
estes formatos; o /docs mostra-os automaticamente.
"""
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field

from app.models.enums import UserRole


# --- Registo ---

class RegisterRequest(BaseModel):
    """
    Dados para registar o primeiro utilizador de uma empresa.

    Neste arranque, o registo cria a empresa e o seu utilizador administrador
    de Capital Humano ao mesmo tempo. Mais tarde, os restantes colaboradores
    serão criados de dentro da plataforma pelo Capital Humano, não por auto-registo.
    """
    company_name: str = Field(..., min_length=2, max_length=200)
    full_name: str = Field(..., min_length=2, max_length=200)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)


# --- Login ---

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# --- Saída de utilizador ---

class UserOut(BaseModel):
    id: int
    company_id: int
    company_name: str | None = None
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    must_change_password: bool = False
    created_at: datetime

    # Permite ao Pydantic ler directamente de objectos SQLAlchemy.
    model_config = {"from_attributes": True}
