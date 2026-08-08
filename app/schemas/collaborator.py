"""
Schemas Pydantic — gestão de colaboradores.

Usados pelo Capital Humano / Administração para cadastrar e gerir os
utilizadores da sua empresa.
"""
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field

from app.models.enums import UserRole


class CollaboratorCreate(BaseModel):
    """
    Dados para o Capital Humano criar um colaborador.

    Nota: quem cria NÃO define a password de outra pessoa. O sistema gera uma
    password temporária e devolve-a uma única vez na resposta, para o CH a
    entregar ao colaborador (que depois a deve alterar).
    """
    full_name: str = Field(..., min_length=2, max_length=200)
    email: EmailStr
    role: UserRole = UserRole.COLABORADOR


class CollaboratorUpdate(BaseModel):
    """Campos editáveis de um colaborador. Todos opcionais (atualização parcial)."""
    full_name: str | None = Field(default=None, min_length=2, max_length=200)
    role: UserRole | None = None
    is_active: bool | None = None


class CollaboratorOut(BaseModel):
    """Representação de um colaborador devolvida pela API."""
    id: int
    company_id: int
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class CollaboratorCreatedOut(BaseModel):
    """
    Resposta ao criar um colaborador: inclui a password temporária gerada.
    Esta é a ÚNICA vez que a password aparece — não é recuperável depois.
    """
    collaborator: CollaboratorOut
    temporary_password: str
