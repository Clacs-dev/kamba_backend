"""
Schemas Pydantic — gestão de colaboradores.
"""
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field

from app.models.enums import UserRole


class CollaboratorCreate(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=200)
    email: EmailStr
    role: UserRole = UserRole.COLABORADOR


class CollaboratorUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=200)
    role: UserRole | None = None
    is_active: bool | None = None


class CollaboratorOut(BaseModel):
    id: int
    company_id: int
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class CollaboratorCreatedOut(BaseModel):
    collaborator: CollaboratorOut
    temporary_password: str