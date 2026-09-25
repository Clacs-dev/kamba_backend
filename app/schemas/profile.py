"""
Schemas Pydantic — ficha detalhada do colaborador (secção 2.1).
"""
from datetime import date, datetime, time
from pydantic import BaseModel, Field, model_validator

from app.models.enums import ContractType, WorkScheduleType


class EducationItem(BaseModel):
    """Uma habilita��ǜo literǭria do colaborador (licenciatura, mestrado, ...)."""
    nivel: str | None = None
    ano_inicio: int | None = Field(default=None, ge=1900, le=2200)
    ano_fim: int | None = Field(default=None, ge=1900, le=2200)
    pais: str | None = None
    instituicao: str | None = Field(default=None, max_length=200)
    curso: str | None = Field(default=None, max_length=200)
    areas: str | None = Field(default=None, max_length=300)


class ExperienceItem(BaseModel):
    """Uma experiência profissional prévia do colaborador."""
    onde: str | None = None
    ano_inicio: int | None = Field(default=None, ge=1900, le=2200)
    ano_fim: int | None = Field(default=None, ge=1900, le=2200)
    funcao: str | None = None


class CertificationItem(BaseModel):
    """Um curso ou certificação do colaborador (alteração 10)."""
    nome: str | None = Field(default=None, max_length=200)
    instituicao: str | None = Field(default=None, max_length=200)
    data: date | None = None
    certificado_url: str | None = Field(default=None, max_length=500)
    validade: date | None = None


class ProfileUpdate(BaseModel):
    """
    Campos da ficha que o Capital Humano preenche/atualiza.
    Todos opcionais: pode preencher-se aos poucos (atualização parcial).
    """
    employee_number: str | None = Field(default=None, max_length=50)
    admission_date: date | None = None
    contract_type: ContractType | None = None
    contract_end_date: date | None = None
    job_category: str | None = Field(default=None, max_length=150)
    job_title: str | None = Field(default=None, max_length=150)
    department: str | None = Field(default=None, max_length=150)
    workplace: str | None = Field(default=None, max_length=150)
    work_schedule: str | None = Field(default=None, max_length=200)

    work_schedule_type: WorkScheduleType | None = None
    fixed_entry_time: time | None = None
    fixed_exit_time: time | None = None
    fixed_break_start: time | None = None
    fixed_break_end: time | None = None
    shift_id: int | None = None

    situation_tags: str | None = Field(default=None, max_length=300)
    nationality: str | None = Field(default=None, max_length=100)
    habilitacoes: str | None = Field(default=None, max_length=200)
    university: str | None = Field(default=None, max_length=200)
    course: str | None = Field(default=None, max_length=200)
    birth_date: date | None = None
    cv: str | None = None
    education: list[EducationItem] | None = None
    experience: list[ExperienceItem] | None = None
    certifications: list[CertificationItem] | None = None

    @model_validator(mode="after")
    def _validar_contrato_e_horario(self) -> "ProfileUpdate":
        # Contrato a termo certo exige data de término, posterior à admissão.
        if self.contract_type == ContractType.TERMO_CERTO:
            if self.contract_end_date is None:
                raise ValueError(
                    "Contrato por tempo determinado exige a data de término."
                )
            if self.admission_date and self.contract_end_date <= self.admission_date:
                raise ValueError(
                    "A data de término do contrato deve ser posterior à data de admissão."
                )

        # Regime de horário: FIXO pede horas de entrada/saída; TURNO pede shift_id.
        if self.work_schedule_type == WorkScheduleType.FIXO:
            if self.fixed_entry_time is None or self.fixed_exit_time is None:
                raise ValueError(
                    "Horário fixo exige hora de entrada e hora de saída."
                )
        elif self.work_schedule_type == WorkScheduleType.TURNO:
            if self.shift_id is None:
                raise ValueError(
                    "Regime de turno exige a seleção de um turno da empresa."
                )
        return self


class ProfileOut(BaseModel):
    """A ficha tal como é devolvida pela API."""
    user_id: int
    company_id: int
    employee_number: str | None
    admission_date: date | None
    contract_type: ContractType | None
    contract_end_date: date | None = None
    job_category: str | None
    job_title: str | None
    department: str | None
    workplace: str | None
    work_schedule: str | None

    work_schedule_type: WorkScheduleType | None = None
    fixed_entry_time: time | None = None
    fixed_exit_time: time | None = None
    fixed_break_start: time | None = None
    fixed_break_end: time | None = None
    shift_id: int | None = None

    situation_tags: str | None
    nationality: str | None
    habilitacoes: str | None
    university: str | None
    course: str | None
    birth_date: date | None = None
    cv: str | None
    education: list[EducationItem] | None = None
    experience: list[ExperienceItem] | None = None
    certifications: list[CertificationItem] | None = None
    photo_url: str | None = None
    policies_signature_pending: bool = False  # calculado: assinaturas em falta
    updated_at: datetime

    model_config = {"from_attributes": True}
