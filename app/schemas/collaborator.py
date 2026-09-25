"""
Schemas Pydantic — gestão de colaboradores.

Usados pelo Capital Humano / Administração para cadastrar e gerir os
utilizadores da sua empresa.
"""
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field

from app.models.enums import UserRole


class CollaboratorRowOut(BaseModel):
    """
    Linha enriquecida da tabela de colaboradores (estrutura KAMBA).

    Junta à conta de acesso os dados da ficha profissional (cargo, direção,
    admissão), as notas dos ciclos de avaliação, e marcadores de situação
    (processo disciplinar ativo / licença). Devolvida pelas listagens.
    """
    id: int
    company_id: int
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime

    # Ficha profissional (EmployeeProfile).
    employee_number: str | None = None
    job_title: str | None = None
    job_category: str | None = None
    department: str | None = None
    admission_year: str | None = None
    situation_tags: str | None = None

    # Ciclos de avaliação da empresa (anos presentes, mais recentes primeiro).
    score_years: list[int] = Field(default_factory=list)
    scores: dict[str, float | None] = Field(default_factory=dict)

    # Marcadores de situação da tabela.
    has_disciplinary: bool = False
    has_leave: bool = False
    company_short: str | None = None


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
    Expõe também o id (e campos) na raiz, para compatibilidade com o frontend
    que espera resp.data.id diretamente.
    """
    id: int
    full_name: str
    email: str
    role: str
    collaborator: CollaboratorOut
    temporary_password: str


class PasswordResetOut(BaseModel):
    """
    Resposta ao redefinir a password de um colaborador.
    A nova password temporária é devolvida uma única vez (não é armazenada em
    texto simples) e o colaborador é obrigado a trocá-la no primeiro acesso.
    """
    id: int
    full_name: str
    email: str
    temporary_password: str
