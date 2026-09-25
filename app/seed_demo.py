import argparse
import json
import os
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func

from app.core.database import Base, SessionLocal, engine
from app.core.schema_migrations import ensure_schema_columns
from app.core.security import hash_password
from app.models import (
    audit,
    career,
    chat,
    collaborator_document,
    compensation,
    company,
    culture_report,
    development,
    disciplinary,
    dossier,
    employee_profile,
    enums,
    evaluation,
    evaluation_settings,
    ficha_correction,
    leave,
    notification,
    occupational,
    onboarding,
    organ,
    shift,
    survey,
    talent,
    training,
    user,
)
from app.models.audit import AuditEvent
from app.models.career import CareerEvent
from app.models.chat import ChatMessage
from app.models.collaborator_document import CollaboratorDocument
from app.models.company import Company
from app.models.compensation import AttendanceRecord, SalaryRecord
from app.models.culture_report import CultureReport
from app.models.development import DevelopmentAction, DevelopmentPlan
from app.models.disciplinary import DisciplinaryCommitteeMember, DisciplinaryProcess
from app.models.dossier import Document, DocumentRead, Signature
from app.models.employee_profile import EmployeeProfile
from app.models.enums import (
    CompanyOrgan,
    ContractType,
    DevelopmentActionStatus,
    DevelopmentPlanStatus,
    DisciplinaryOutcome,
    DisciplinaryPhase,
    EvaluationCategory,
    EvaluationPhase,
    FitnessResult,
    LeaveStatus,
    LeaveType,
    PotentialLevel,
    ReadinessLevel,
    SignatureType,
    SurveyStatus,
    TrainingActionStatus,
    TrainingPlanStatus,
    TrainingSource,
    UserRole,
    WorkScheduleType,
    DocumentType,
    CareerEventType,
    CommitteeRole,
)
from app.models.evaluation import Evaluation, EvaluationCycle
from app.models.evaluation_settings import EvaluationSettings
from app.models.ficha_correction import FichaCorrectionRequest
from app.models.leave import LeaveRequest
from app.models.notification import Notification
from app.models.occupational import OccupationalExam
from app.models.onboarding import OnboardingItem
from app.models.organ import OrganMember
from app.models.shift import Shift
from app.models.survey import Survey, SurveyParticipation, SurveyResponse
from app.models.talent import SuccessionPlan, TalentMatrix
from app.models.training import TrainingAction, TrainingPlan
from app.models.user import User

NOW = datetime.now(timezone.utc)
TODAY = date.today()
SURVEY_TITLE = "Inquérito-pulso — Demonstração KAMBA 2026"

COLLABORATOR_ROWS = [
    ("Ana Miguel", "Técnica de Vendas", "DCO — Vendas", "Técnica"),
    ("Bruno Domingos", "Assistente Comercial", "DCO — Vendas", "Assistente"),
    ("Carla Nsue", "Técnica de Seguro de Vida", "DCO — Seguros", "Técnica"),
    ("Dário Nascimento", "Técnico de Sinistros", "DTO — Sinistros", "Técnico"),
    ("Edna Bengui", "Assistente Administrativa", "DGA — Administração Geral", "Assistente"),
    ("Ernesto Kiala", "Técnico de Riscos", "DGA — Riscos", "Técnico"),
    ("Fátima Domingos", "Analista de Reclamações", "DTO — Sinistros", "Analista"),
    ("Hugo Baptista", "Técnico de Informática", "DSI — Sistemas de Informação", "Técnico"),
    ("Isabel Neto", "Contabilista", "DFI — Finanças", "Contabilista"),
    ("João Kambamba", "Assistente de Tesouraria", "DFI — Finanças", "Assistente"),
    ("Lara Portuguese", "Técnica de Recursos Humanos", "DCH — Capital Humano", "Técnica"),
    ("Manuel Sebastião", "Técnico de Arquivo", "DGA — Administração Geral", "Técnico"),
    ("Nádia Fortunato", "Técnica de Formação", "DCH — Capital Humano", "Técnica"),
    ("Osvaldo Kalunga", "Técnico de Segurança", "DSO — Segurança", "Técnico"),
    ("Paula Xavier", "Técnica de Comunicação", "DCO — Marketing", "Técnica"),
    ("Quim Manuel", "Assistente de Logística", "DCO — Vendas", "Assistente"),
    ("Rosa Muanza", "Técnica Administrativa", "DGA — Administração Geral", "Técnica"),
    ("Samuel Pedro", "Analista de Dados", "DSI — Sistemas de Informação", "Analista"),
    ("Teresa Kiala", "Técnica de Conformidade", "DGA — Conformidade", "Técnica"),
    ("Vasco Nzuzi", "Técnico de Cobranças", "DFI — Finanças", "Técnico"),
]

DIRECTOR_ROWS = [
    ("Alberto Domingos", "Director Comercial", "DCO — Vendas"),
    ("Benedito Kiala", "Director de Sinistros", "DTO — Sinistros"),
    ("Clara Nsue", "Director de Sistemas", "DSI — Sistemas de Informação"),
    ("Daniel Muanza", "Director Financeiro", "DFI — Finanças"),
    ("Esperança Neto", "Director de Administração", "DGA — Administração Geral"),
]

STAFF_ROWS = [
    ("Helena Kambamba", "Capital Humano", "DCH — Capital Humano", UserRole.CAPITAL_HUMANO),
    ("Marta Quissanga", "Membro da Comissão de Avaliação", "DCA — Avaliação", UserRole.COMISSAO_AVALIACAO),
    ("Nuno Sebastião", "Administração", "DGA — Administração", UserRole.ADMINISTRACAO),
]


def build_specs(include_platform_admin=False):
    specs = []
    for index, (full_name, title, department, category) in enumerate(COLLABORATOR_ROWS, 1):
        specs.append({
            "key": f"colaborador-{index:02d}",
            "email": f"demo.colaborador{index:02d}@kamba-demo.com",
            "full_name": full_name,
            "role": UserRole.COLABORADOR,
            "title": title,
            "department": department,
            "category": category,
            "index": index,
        })
    for index, (full_name, title, department) in enumerate(DIRECTOR_ROWS, 1):
        specs.append({
            "key": f"director-{index:02d}",
            "email": f"demo.director{index:02d}@kamba-demo.com",
            "full_name": full_name,
            "role": UserRole.DIRECTOR,
            "title": title,
            "department": department,
            "category": "Dirigente",
            "index": index,
        })
    for index, (full_name, title, department, role) in enumerate(STAFF_ROWS, 1):
        key = {
            UserRole.CAPITAL_HUMANO: "capital-humano",
            UserRole.COMISSAO_AVALIACAO: "comissao-avaliacao",
            UserRole.ADMINISTRACAO: "administracao",
        }[role]
        specs.append({
            "key": key,
            "email": f"demo.{key}@kamba-demo.com",
            "full_name": full_name,
            "role": role,
            "title": title,
            "department": department,
            "category": "Gestão",
            "index": index,
        })
    if include_platform_admin:
        specs.append({
            "key": "admin-plataforma",
            "email": "demo.admin@kamba-demo.com",
            "full_name": "Administrador de Plataforma",
            "role": UserRole.ADMIN,
            "title": "Administração de Plataforma",
            "department": "DGA — Administração Geral",
            "category": "Gestão",
            "index": 99,
        })
    return specs


def _parse_args():
    parser = argparse.ArgumentParser(description="Popula uma empresa KAMBA com dados de demonstração")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--company-id", type=int)
    target.add_argument("--company-name")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--confirm-demo", action="store_true")
    parser.add_argument("--skip-business-data", action="store_true")
    parser.add_argument("--keep-existing-passwords", action="store_true")
    parser.add_argument("--include-platform-admin", action="store_true")
    return parser.parse_args()


def _find_company(db, company_id=None, company_name=None):
    if company_id is not None:
        company = db.query(Company).filter(Company.id == company_id).first()
        if company is None:
            raise RuntimeError(f"Empresa com ID {company_id} não encontrada.")
        return company
    company = db.query(Company).filter(func.lower(Company.name) == company_name.strip().lower()).first()
    if company is not None:
        return company
    company = Company(
        name=company_name.strip(),
        plan="empresarial",
        is_active=True,
        vision="Construir uma organização mais justa, produtiva e sustentável.",
        mission="Desenvolver pessoas e transformar resultados em valor para clientes e colaboradores.",
        values="Ética, respeito, colaboração, responsabilidade e inovação.",
        objectives="Melhorar a experiência das pessoas, a qualidade do serviço e a eficiência operacional.",
        uses_shifts=True,
    )
    db.add(company)
    db.flush()
    return company


def _fill_company(company):
    if not company.vision:
        company.vision = "Construir uma organização mais justa, produtiva e sustentável."
    if not company.mission:
        company.mission = "Desenvolver pessoas e transformar resultados em valor."
    if not company.values:
        company.values = "Ética, respeito, colaboração, responsabilidade e inovação."
    if not company.objectives:
        company.objectives = "Melhorar a experiência das pessoas e a eficiência operacional."
    company.is_active = True
    company.uses_shifts = True


def _next_employee_number(db, company_id):
    values = db.query(EmployeeProfile.employee_number).filter(
        EmployeeProfile.company_id == company_id,
        EmployeeProfile.employee_number.isnot(None),
    ).all()
    numbers = []
    for (value,) in values:
        try:
            numbers.append(int(str(value).lstrip("0") or "0"))
        except (TypeError, ValueError):
            continue
    return f"{(max(numbers) + 1) if numbers else 1:04d}"


def _profile_for(db, user, company):
    profile = db.query(EmployeeProfile).filter(EmployeeProfile.user_id == user.id).first()
    if profile is None:
        profile = EmployeeProfile(user_id=user.id, company_id=company.id)
        db.add(profile)
        db.flush()
    return profile


def _date_for_index(index, first_year):
    year = first_year + (index % 10)
    month = (index * 3) % 12 + 1
    day = (index * 7) % 27 + 1
    return date(year, month, day)


def _populate_profile(db, user, company, spec, shifts):
    profile = _profile_for(db, user, company)
    if not profile.employee_number:
        profile.employee_number = _next_employee_number(db, company.id)
    index = spec["index"]
    is_director = spec["role"] == UserRole.DIRECTOR
    is_privileged = spec["role"] not in (UserRole.COLABORADOR, UserRole.DIRECTOR)
    contract_type = ContractType.TERMO_CERTO if index in (7, 15) else ContractType.EFETIVO
    schedule_type = WorkScheduleType.TURNO if not is_privileged and index % 5 == 0 else WorkScheduleType.FIXO
    shift_name = ("Manhã", "Tarde", "Noite")[(index - 1) % 3]
    profile.admission_date = _date_for_index(index, 2015 if not is_privileged else 2012)
    profile.contract_type = contract_type
    profile.contract_end_date = date(2027, 12, 31) if contract_type == ContractType.TERMO_CERTO else None
    profile.job_category = spec["category"]
    profile.job_title = spec["title"]
    profile.department = spec["department"]
    profile.workplace = "Luanda — Sede"
    profile.work_schedule = "Segunda a sexta, 08:00–17:00" if schedule_type == WorkScheduleType.FIXO else f"Turno {shift_name}"
    profile.work_schedule_type = schedule_type
    profile.fixed_entry_time = time(8, 0) if schedule_type == WorkScheduleType.FIXO else None
    profile.fixed_exit_time = time(17, 0) if schedule_type == WorkScheduleType.FIXO else None
    profile.fixed_break_start = time(12, 0) if schedule_type == WorkScheduleType.FIXO else None
    profile.fixed_break_end = time(13, 0) if schedule_type == WorkScheduleType.FIXO else None
    profile.shift_id = shifts[shift_name].id if schedule_type == WorkScheduleType.TURNO else None
    profile.situation_tags = "Ativo"
    profile.nationality = "Angolana"
    profile.habilitacoes = "Licenciatura"
    profile.university = "Universidade Agostinho Neto"
    profile.course = spec["title"]
    profile.birth_date = _date_for_index(index + 3, 1980)
    profile.cv = (
        f"{spec['full_name']} exerce o cargo de {spec['title']} na {company.name}. "
        "A sua ficha contém formação, experiência, certificações e histórico profissional para demonstração."
    )
    profile.education = [{
        "nivel": "Licenciatura",
        "ano_inicio": 2007 + (index % 5),
        "ano_fim": 2011 + (index % 5),
        "pais": "Angola",
        "instituicao": profile.university,
        "curso": spec["title"],
        "areas": "Gestão, planeamento e comunicação",
    }]
    profile.experience = [
        {"onde": "Empresa anterior", "ano_inicio": 2012 + (index % 4), "ano_fim": 2018, "funcao": "Técnico de área"},
        {"onde": company.name, "ano_inicio": profile.admission_date.year, "ano_fim": None, "funcao": spec["title"]},
    ]
    profile.certifications = [{
        "nome": "Formação em segurança e compliance",
        "instituicao": "KAMBA Academy",
        "data": "2025",
        "certificado_url": None,
        "validade": "2028",
    }]
    profile.photo_url = None
    if is_director:
        profile.situation_tags = "Ativo;Gestão de equipa"
    db.flush()
    return profile


def _upsert_user(db, company, spec, password_hash, reset_passwords):
    user = db.query(User).filter(
        User.company_id == company.id,
        User.email == spec["email"],
    ).first()
    created = user is None
    if user is None:
        user = User(
            company_id=company.id,
            email=spec["email"],
            hashed_password=password_hash,
            full_name=spec["full_name"],
            role=spec["role"],
            is_active=True,
            must_change_password=False,
        )
        db.add(user)
    else:
        user.full_name = spec["full_name"]
        user.role = spec["role"]
        user.is_active = True
        if reset_passwords:
            user.hashed_password = password_hash
            user.must_change_password = False
    db.flush()
    return user, created


def _ensure_shifts(db, company):
    definitions = [
        ("Manhã", time(8, 0), time(16, 0), time(12, 0), time(13, 0)),
        ("Tarde", time(14, 0), time(22, 0), time(18, 0), time(19, 0)),
        ("Noite", time(22, 0), time(6, 0), time(2, 0), time(3, 0)),
    ]
    result = {}
    for name, start, end, break_start, break_end in definitions:
        shift = db.query(Shift).filter(Shift.company_id == company.id, Shift.name == name).first()
        if shift is None:
            shift = Shift(
                company_id=company.id,
                name=name,
                start_time=start,
                end_time=end,
                break_start=break_start,
                break_end=break_end,
                is_active=True,
            )
            db.add(shift)
            db.flush()
        else:
            shift.is_active = True
        result[name] = shift
    company.uses_shifts = True
    db.flush()
    return result


def _ensure_settings(db, company):
    settings = db.query(EvaluationSettings).filter(EvaluationSettings.company_id == company.id).first()
    if settings is None:
        settings = EvaluationSettings(
            company_id=company.id,
            cycle_calendar="Janeiro a Dezembro",
            appeal_deadline_days=8,
        )
        db.add(settings)
        db.flush()
    else:
        settings.appeal_deadline_days = settings.appeal_deadline_days or 8
        settings.cycle_calendar = settings.cycle_calendar or "Janeiro a Dezembro"
    return settings


def _ensure_cycle(db, company, name, is_open):
    cycle = db.query(EvaluationCycle).filter(
        EvaluationCycle.company_id == company.id,
        EvaluationCycle.name == name,
    ).first()
    if cycle is None:
        cycle = EvaluationCycle(company_id=company.id, name=name, is_open=is_open)
        db.add(cycle)
        db.flush()
    else:
        cycle.is_open = is_open
    return cycle


def _director_for(accounts, collaborator):
    director = None
    for spec, user in accounts:
        if user.id == collaborator.id or spec["role"] != UserRole.DIRECTOR:
            continue
        profile = user.profile
        if profile and profile.department == collaborator.profile.department:
            return user
        if director is None:
            director = user
    return director or next(user for _, user in accounts if user.role == UserRole.DIRECTOR)


def _objectives(index):
    return json.dumps([
        {"objetivo": "Cumprir os resultados da área", "peso": 40},
        {"objetivo": "Melhorar a qualidade do serviço", "peso": 35},
        {"objetivo": "Partilhar conhecimento com a equipa", "peso": 25},
    ])


def _answers(index, director=False):
    return json.dumps({
        "pontuacoes": [3 + (index % 3), 4 + (index % 2), 3],
        "comentario": "Desempenho consistente, com oportunidades de desenvolvimento.",
    })


def _seed_evaluations(db, company, accounts, cycles):
    targets = [(spec, user) for spec, user in accounts if spec["role"] in (UserRole.COLABORADOR, UserRole.DIRECTOR)]
    phases = [
        EvaluationPhase.AUTOAVALIACAO,
        EvaluationPhase.AVALIACAO_DIRECTOR,
        EvaluationPhase.CONCORDANCIA,
        EvaluationPhase.COMISSAO,
        EvaluationPhase.FECHADA,
        EvaluationPhase.VALIDADA,
    ]
    for cycle_index, cycle in enumerate(cycles):
        for index, (spec, user) in enumerate(targets):
            evaluation = db.query(Evaluation).filter(
                Evaluation.cycle_id == cycle.id,
                Evaluation.collaborator_id == user.id,
            ).first()
            if evaluation is None:
                is_director = spec["role"] == UserRole.DIRECTOR
                phase = EvaluationPhase.VALIDADA if cycle_index == 0 else phases[index % len(phases)]
                director = _director_for(accounts, user)
                score = 3.1 + ((index * 7 + cycle_index) % 16) / 10
                final_score = score if phase in (EvaluationPhase.FECHADA, EvaluationPhase.VALIDADA) else None
                classification = None
                if final_score is not None:
                    classification = "Excelente" if final_score >= 4.5 else "Bom" if final_score >= 3.5 else "Satisfatório"
                evaluation = Evaluation(
                    company_id=company.id,
                    cycle_id=cycle.id,
                    collaborator_id=user.id,
                    director_id=director.id,
                    category=EvaluationCategory.DIRIGENTE if is_director else EvaluationCategory.TECNICO,
                    phase=phase,
                    self_answers=_answers(index),
                    director_answers=_answers(index + 1, director=is_director),
                    final_score=final_score,
                    classification=classification,
                    appeal_reason="Solicita revisão do resultado da avaliação." if phase == EvaluationPhase.COMISSAO else None,
                    appeal_deadline=NOW + timedelta(days=5) if phase == EvaluationPhase.COMISSAO else None,
                    cycle_adjusted=index % 9 == 0,
                    commission_decision="Decisão da comissão registada para efeitos de demonstração." if phase == EvaluationPhase.COMISSAO else None,
                    defined_objectives=_objectives(index),
                )
                db.add(evaluation)
    db.flush()


def _seed_leave(db, company, accounts):
    collaborators = [user for spec, user in accounts if spec["role"] == UserRole.COLABORADOR]
    rows = [
        (0, LeaveType.FERIAS, TODAY + timedelta(days=18), 10, LeaveStatus.PENDENTE_DIR, False, "Férias anuais — pedido em análise"),
        (1, LeaveType.FERIAS, TODAY - timedelta(days=50), 8, LeaveStatus.APROVADA, True, "Férias anuais"),
        (2, LeaveType.FALTA, TODAY - timedelta(days=12), 1, LeaveStatus.JUSTIFICADA, False, "Atestado médico apresentado"),
        (3, LeaveType.DOENCA, TODAY - timedelta(days=80), 15, LeaveStatus.APROVADA, True, "Afastamento por doença"),
        (4, LeaveType.FERIAS, TODAY - timedelta(days=100), 12, LeaveStatus.RECUSADA, False, "Período com sobreposição de equipa"),
        (5, LeaveType.MATERNIDADE, TODAY - timedelta(days=200), 90, LeaveStatus.APROVADA, True, "Licença de maternidade"),
    ]
    for index, leave_type, start, days, status, averbado, reason in rows:
        if index >= len(collaborators):
            continue
        user = collaborators[index]
        existing = db.query(LeaveRequest).filter(
            LeaveRequest.company_id == company.id,
            LeaveRequest.collaborator_id == user.id,
            LeaveRequest.leave_type == leave_type,
            LeaveRequest.start_date == start,
        ).first()
        if existing is None:
            db.add(LeaveRequest(
                company_id=company.id,
                collaborator_id=user.id,
                leave_type=leave_type,
                start_date=start,
                end_date=start + timedelta(days=days - 1),
                days=days,
                reason=reason,
                status=status,
                rejection_reason="Período já atribuído a outro elemento da equipa." if status == LeaveStatus.RECUSADA else None,
                averbado=averbado,
                document_name="Atestado de demonstração.pdf" if leave_type == LeaveType.FALTA else None,
            ))
    db.flush()


def _seed_training(db, company, accounts):
    plan = db.query(TrainingPlan).filter(
        TrainingPlan.company_id == company.id,
        TrainingPlan.name == "Plano de Formação 2026",
    ).first()
    if plan is None:
        plan = TrainingPlan(company_id=company.id, name="Plano de Formação 2026", status=TrainingPlanStatus.EM_EXECUCAO)
        db.add(plan)
        db.flush()
    collaborators = [user for spec, user in accounts if spec["role"] == UserRole.COLABORADOR]
    actions = [
        (0, "Liderança e comunicação", "Formação em comunicação e feedback", TrainingSource.AREA, TrainingActionStatus.CONCLUIDA),
        (1, "Excel avançado", "Automação de relatórios de equipa", TrainingSource.SISTEMA, TrainingActionStatus.CONCLUIDA),
        (2, "Segurança no trabalho", "Prevenção e proteção no trabalho", TrainingSource.SISTEMA, TrainingActionStatus.APROVADA),
        (3, "Gestão de conflitos", "Resolução constructive de conflitos", TrainingSource.AREA, TrainingActionStatus.PROPOSTA),
        (4, "Atendimento ao cliente", "Experiência do cliente e comunicação", TrainingSource.AREA, TrainingActionStatus.APROVADA),
    ]
    for index, title, description, source, status in actions:
        user = collaborators[index % len(collaborators)]
        existing = db.query(TrainingAction).filter(
            TrainingAction.plan_id == plan.id,
            TrainingAction.collaborator_id == user.id,
            TrainingAction.title == title,
        ).first()
        if existing is None:
            db.add(TrainingAction(
                company_id=company.id,
                plan_id=plan.id,
                collaborator_id=user.id,
                title=title,
                description=description,
                source=source,
                status=status,
            ))
    db.flush()


def _seed_development(db, company, accounts):
    collaborators = [user for spec, user in accounts if spec["role"] == UserRole.COLABORADOR]
    creator = next(user for spec, user in accounts if spec["role"] == UserRole.CAPITAL_HUMANO)
    for index, user in enumerate(collaborators[:8]):
        plan = db.query(DevelopmentPlan).filter(
            DevelopmentPlan.company_id == company.id,
            DevelopmentPlan.collaborator_id == user.id,
            DevelopmentPlan.year == 2026,
        ).first()
        if plan is None:
            plan = DevelopmentPlan(
                company_id=company.id,
                collaborator_id=user.id,
                year=2026,
                status=DevelopmentPlanStatus.ABERTO,
                created_by=creator.id,
            )
            db.add(plan)
            db.flush()
            db.add_all([
                DevelopmentAction(
                    company_id=company.id,
                    plan_id=plan.id,
                    title="Mentoria com a chefia",
                    description="Sessões quinzenais de acompanhamento.",
                    status=DevelopmentActionStatus.PENDENTE,
                ),
                DevelopmentAction(
                    company_id=company.id,
                    plan_id=plan.id,
                    title="Curso de especialização",
                    status=DevelopmentActionStatus.CONCLUIDA,
                ),
            ])
    db.flush()


def _seed_career_and_compensation(db, company, accounts):
    collaborators = [user for spec, user in accounts if spec["role"] == UserRole.COLABORADOR]
    career_rows = [
        (0, CareerEventType.LOUVOR, "Reconhecimento pelo desempenho", date(2025, 6, 20)),
        (1, CareerEventType.PROMOCAO, "Promoção a especialista", date(2025, 11, 1)),
        (2, CareerEventType.NOMEACAO, "Nomeação para projeto transversal", date(2026, 2, 10)),
    ]
    for index, event_type, title, event_date in career_rows:
        user = collaborators[index]
        existing = db.query(CareerEvent).filter(
            CareerEvent.company_id == company.id,
            CareerEvent.collaborator_id == user.id,
            CareerEvent.title == title,
        ).first()
        if existing is None:
            db.add(CareerEvent(
                company_id=company.id,
                collaborator_id=user.id,
                event_type=event_type,
                event_date=event_date,
                title=title,
                description="Marco profissional criado para a apresentação da plataforma.",
            ))
    for index, user in enumerate(collaborators):
        for year, salary in ((2025, 280000 + index * 15000), (2026, 310000 + index * 18000)):
            existing = db.query(SalaryRecord).filter(
                SalaryRecord.company_id == company.id,
                SalaryRecord.collaborator_id == user.id,
                SalaryRecord.year == year,
            ).first()
            if existing is None:
                db.add(SalaryRecord(
                    company_id=company.id,
                    collaborator_id=user.id,
                    year=year,
                    gross_salary=salary,
                    salary_grade="Técnico I" if index % 3 else "Técnico II",
                ))
        attendance = db.query(AttendanceRecord).filter(
            AttendanceRecord.company_id == company.id,
            AttendanceRecord.collaborator_id == user.id,
            AttendanceRecord.period == "2025",
        ).first()
        if attendance is None:
            db.add(AttendanceRecord(
                company_id=company.id,
                collaborator_id=user.id,
                period="2025",
                present_days=238 - (index % 4),
                justified_absences=2 + (index % 4),
                unjustified_absences=index % 2,
                vacation_days_taken=20 + (index % 8),
            ))
    for index, user in enumerate(collaborators):
        exam = db.query(OccupationalExam).filter(
            OccupationalExam.company_id == company.id,
            OccupationalExam.collaborator_id == user.id,
        ).first()
        if exam is None:
            db.add(OccupationalExam(
                company_id=company.id,
                collaborator_id=user.id,
                fitness=FitnessResult.APTO,
                exam_date=date(2026, 1, 10 + index),
                next_exam_date=date(2027, 1, 10 + index),
            ))
    db.flush()


def _seed_onboarding_and_corrections(db, company, accounts):
    collaborators = [user for spec, user in accounts if spec["role"] == UserRole.COLABORADOR]
    descriptions = [
        "Receção do equipamento de trabalho",
        "Acesso ao email e aos sistemas",
        "Apresentação da equipa e da cultura",
        "Formação inicial de segurança",
    ]
    for user in collaborators:
        for description in descriptions:
            existing = db.query(OnboardingItem).filter(
                OnboardingItem.company_id == company.id,
                OnboardingItem.collaborator_id == user.id,
                OnboardingItem.description == description,
            ).first()
            if existing is None:
                db.add(OnboardingItem(
                    company_id=company.id,
                    collaborator_id=user.id,
                    description=description,
                    done=True,
                    applicable=True,
                    delivered=True,
                ))
    pending_user = collaborators[0]
    correction = db.query(FichaCorrectionRequest).filter(
        FichaCorrectionRequest.company_id == company.id,
        FichaCorrectionRequest.collaborator_id == pending_user.id,
        FichaCorrectionRequest.status == "pendente",
    ).first()
    if correction is None:
        db.add(FichaCorrectionRequest(
            company_id=company.id,
            collaborator_id=pending_user.id,
            message="Solicito a atualização da designação da direção na ficha.",
            status="pendente",
        ))
    db.flush()


def _seed_dossier(db, company, accounts):
    documents = [
        ("Contrato de Trabalho", DocumentType.CONTRATO, "Regula a relação laboral e os direitos e deveres das partes."),
        ("Regulamento Interno", DocumentType.REGULAMENTO_INTERNO, "Normas de funcionamento, ética e organização da empresa."),
        ("Código de Ética", DocumentType.CODIGO_ETICA, "Princípios de conduta, integridade e respeito."),
        ("Política de Assiduidade", DocumentType.POLITICA_ASSIDUIDADE, "Regras de assiduidade, pontualidade e comunicação de ausências."),
        ("Política de Remuneração", DocumentType.POLITICA_REMUNERACAO, "Critérios de enquadramento e progressão salarial."),
        ("Regulamento de Avaliação", DocumentType.REGULAMENTO_AVALIACAO, "Regras do ciclo anual de avaliação de desempenho."),
        ("Manual de Acolhimento", DocumentType.OUTRO, "Guia de integração de novos colaboradores."),
    ]
    stored = {}
    for title, doc_type, content in documents:
        document = db.query(Document).filter(
            Document.company_id == company.id,
            Document.title == title,
        ).first()
        if document is None:
            document = Document(company_id=company.id, title=title, doc_type=doc_type, content=content)
            db.add(document)
            db.flush()
        stored[title] = document
    users = [user for _, user in accounts if user.role in (UserRole.COLABORADOR, UserRole.DIRECTOR)]
    for user in users:
        for document in list(stored.values())[:3]:
            read = db.query(DocumentRead).filter(
                DocumentRead.company_id == company.id,
                DocumentRead.document_id == document.id,
                DocumentRead.user_id == user.id,
            ).first()
            if read is None:
                db.add(DocumentRead(company_id=company.id, document_id=document.id, user_id=user.id))
        for signature_type in SignatureType:
            signature = db.query(Signature).filter(
                Signature.company_id == company.id,
                Signature.user_id == user.id,
                Signature.signature_type == signature_type,
            ).first()
            if signature is None:
                db.add(Signature(company_id=company.id, user_id=user.id, signature_type=signature_type))
    db.flush()


def _seed_survey_and_culture(db, company, accounts):
    survey = db.query(Survey).filter(
        Survey.company_id == company.id,
        Survey.title == SURVEY_TITLE,
    ).first()
    if survey is None:
        survey = Survey(
            company_id=company.id,
            title=SURVEY_TITLE,
            dimensions=json.dumps([
                "confianca_lideranca",
                "clareza_estrategica",
                "reconhecimento",
                "equilibrio_vida",
                "recomendaria_empresa",
            ]),
            status=SurveyStatus.ABERTO,
        )
        db.add(survey)
        db.flush()
    response_count = db.query(SurveyResponse).filter(
        SurveyResponse.company_id == company.id,
        SurveyResponse.survey_id == survey.id,
    ).count()
    if response_count == 0:
        for index in range(10):
            db.add(SurveyResponse(
                company_id=company.id,
                survey_id=survey.id,
                answers=json.dumps({
                    "confianca_lideranca": 3 + (index % 3),
                    "clareza_estrategica": 3 + ((index + 1) % 3),
                    "reconhecimento": 3 + ((index + 2) % 3),
                    "equilibrio_vida": 3 + ((index + 1) % 2),
                    "recomendaria_empresa": 4 if index % 3 else 5,
                }),
            ))
    collaborators = [user for spec, user in accounts if spec["role"] == UserRole.COLABORADOR]
    for user in collaborators[:15]:
        participation = db.query(SurveyParticipation).filter(
            SurveyParticipation.company_id == company.id,
            SurveyParticipation.survey_id == survey.id,
            SurveyParticipation.user_id == user.id,
        ).first()
        if participation is None:
            db.add(SurveyParticipation(company_id=company.id, survey_id=survey.id, user_id=user.id))
    report = db.query(CultureReport).filter(CultureReport.company_id == company.id).first()
    if report is None:
        report = CultureReport(company_id=company.id)
        db.add(report)
    report.enps = report.enps or "+50"
    report.participation = report.participation or "75%"
    report.pulses_note = report.pulses_note or "Pulso trimestral com participação acima do mínimo de revelação."
    report.dimensions_json = report.dimensions_json or json.dumps([
        {"name": "Confiança na liderança", "y2024": 61, "y2025": 69, "y2026": 76},
        {"name": "Clareza estratégica", "y2024": 58, "y2025": 67, "y2026": 74},
        {"name": "Reconhecimento", "y2024": 55, "y2025": 65, "y2026": 72},
    ])
    report.recommendations_json = report.recommendations_json or json.dumps([
        "Reforçar a comunicação das prioridades trimestrais.",
        "Aumentar o reconhecimento público das equipas.",
        "Manter o programa de mentoria para sucessão.",
    ])
    db.flush()


def _seed_notifications_and_chat(db, company, accounts):
    by_key = {spec["key"]: user for spec, user in accounts}
    ch = by_key["capital-humano"]
    director = by_key["director-01"]
    collaborator = next(user for spec, user in accounts if spec["role"] == UserRole.COLABORADOR)
    notifications = [
        (ch, "Ciclo de avaliação 2026 aberto", "O ciclo anual está disponível para os colaboradores.", "avaliacao", "/avaliacoes", False),
        (director, "Novo pedido de férias", " existe um pedido de férias para analisar.", "ferias", "/ausencias", False),
        (collaborator, "Plano de formação disponível", "Consulte as ações de formação do seu plano.", "formacao", "/formacao", True),
    ]
    for user, title, message, category, link, is_read in notifications:
        existing = db.query(Notification).filter(
            Notification.company_id == company.id,
            Notification.user_id == user.id,
            Notification.title == title,
        ).first()
        if existing is None:
            db.add(Notification(
                company_id=company.id,
                user_id=user.id,
                title=title,
                message=message.strip(),
                category=category,
                link=link,
                is_read=is_read,
            ))
    messages = [
        (ch.id, director.id, "Bom dia. O ciclo de avaliação já está disponível para as equipas.", False),
        (director.id, ch.id, "Bom dia. A equipa de Vendas já começa a organizar os objetivos.", True),
        (director.id, collaborator.id, "A sua autoavaliação está pendente. Pode submeter quando estiver concluída.", False),
    ]
    for sender, recipient, body, is_read in messages:
        existing = db.query(ChatMessage).filter(
            ChatMessage.company_id == company.id,
            ChatMessage.sender_id == sender,
            ChatMessage.recipient_id == recipient,
            ChatMessage.body == body,
        ).first()
        if existing is None:
            db.add(ChatMessage(
                company_id=company.id,
                sender_id=sender,
                recipient_id=recipient,
                body=body,
                is_read=is_read,
                created_at=NOW - timedelta(hours=len(messages) * 2),
            ))
    db.flush()


def _seed_organ_and_disciplinary(db, company, accounts):
    directors = [user for spec, user in accounts if spec["role"] == UserRole.DIRECTOR]
    organ_roles = {
        CompanyOrgan.CONSELHO_ADMINISTRACAO: "Presidente",
        CompanyOrgan.COMISSAO_EXECUTIVA: "Director Executivo",
        CompanyOrgan.CONSELHO_FISCAL: "Membro",
        CompanyOrgan.MESA_ASSEMBLEIA: "Secretário",
    }
    for index, user in enumerate(directors):
        organ = list(organ_roles)[index % len(organ_roles)]
        existing = db.query(OrganMember).filter(
            OrganMember.company_id == company.id,
            OrganMember.organ == organ,
            OrganMember.user_id == user.id,
        ).first()
        if existing is None:
            db.add(OrganMember(
                company_id=company.id,
                organ=organ,
                user_id=user.id,
                organ_role=organ_roles[organ],
            ))
    collaborators = [user for spec, user in accounts if spec["role"] == UserRole.COLABORADOR]
    accused = collaborators[0]
    instructor = next(user for spec, user in accounts if spec["role"] == UserRole.CAPITAL_HUMANO)
    process = db.query(DisciplinaryProcess).filter(
        DisciplinaryProcess.company_id == company.id,
        DisciplinaryProcess.reference == "DEMO-2026-001",
    ).first()
    if process is None:
        process = DisciplinaryProcess(
            company_id=company.id,
            accused_id=accused.id,
            instructor_id=instructor.id,
            reference="DEMO-2026-001",
            phase=DisciplinaryPhase.ARQUIVADO,
            imputed_facts="Registo demonstrativo de factos disciplinares concluídos.",
            disciplinary_record="Sem antecedentes relevantes.",
            charge_note="Nota de culpa recebida.",
            preventive_suspension=False,
            defense_text="Defesa apresentada e analisada.",
            decision_text="Processo arquivado sem medida disciplinar.",
            outcome=DisciplinaryOutcome.ARQUIVAMENTO,
        )
        db.add(process)
        db.flush()
    committee_roles = [CommitteeRole.RELATOR, CommitteeRole.INSTRUTOR, CommitteeRole.PRESIDENTE]
    for index, user in enumerate(directors[:3]):
        existing = db.query(DisciplinaryCommitteeMember).filter(
            DisciplinaryCommitteeMember.process_id == process.id,
            DisciplinaryCommitteeMember.user_id == user.id,
        ).first()
        if existing is None:
            db.add(DisciplinaryCommitteeMember(
                process_id=process.id,
                user_id=user.id,
                role=committee_roles[index],
            ))
    db.flush()


def _seed_talent(db, company, accounts, cycle):
    collaborators = [user for spec, user in accounts if spec["role"] == UserRole.COLABORADOR]
    creator = next(user for spec, user in accounts if spec["role"] == UserRole.CAPITAL_HUMANO)
    potentials = [PotentialLevel.ALTO, PotentialLevel.MEDIO, PotentialLevel.MEDIO, PotentialLevel.BAIXO]
    for index, user in enumerate(collaborators):
        existing = db.query(TalentMatrix).filter(
            TalentMatrix.cycle_id == cycle.id,
            TalentMatrix.collaborator_id == user.id,
        ).first()
        if existing is None:
            db.add(TalentMatrix(
                company_id=company.id,
                cycle_id=cycle.id,
                collaborator_id=user.id,
                potential=potentials[index % len(potentials)],
                position=index % 2 == 0 and "Alto potencial" or "Desempenho consistente",
                risk_of_exit=index % 8 == 0,
                notes="Mapeamento criado para demonstração do comité de talento.",
                created_by=creator.id,
            ))
    for index, role_title in enumerate(("Director Comercial", "Director Financeiro", "Director de Sistemas")):
        existing = db.query(SuccessionPlan).filter(
            SuccessionPlan.company_id == company.id,
            SuccessionPlan.role_title == role_title,
        ).first()
        if existing is None:
            db.add(SuccessionPlan(
                company_id=company.id,
                role_title=role_title,
                incumbent_id=None,
                successor_id=collaborators[index].id,
                readiness=ReadinessLevel.EM_12_MESES,
                risk_of_exit=index == 0,
                notes="Plano de sucessão demonstrativo.",
                created_by=creator.id,
            ))
    db.flush()


def _seed_audit_and_documents(db, company, accounts):
    actor = next(user for spec, user in accounts if spec["role"] == UserRole.CAPITAL_HUMANO)
    events = [
        ("demo.perfil_atualizado", "Perfis de demonstração atualizados."),
        ("demo.avaliacao_ciclo", "Ciclo de avaliação 2026 preparado."),
        ("demo.formacao_publicada", "Plano de formação 2026 publicado."),
    ]
    for action, detail in events:
        existing = db.query(AuditEvent).filter(
            AuditEvent.company_id == company.id,
            AuditEvent.action == action,
            AuditEvent.detail == detail,
        ).first()
        if existing is None:
            db.add(AuditEvent(
                company_id=company.id,
                actor_id=actor.id,
                actor_name=actor.full_name,
                actor_role=actor.role.value,
                action=action,
                detail=detail,
            ))
    collaborators = [user for spec, user in accounts if spec["role"] == UserRole.COLABORADOR]
    for index, user in enumerate(collaborators[:8]):
        for doc_type, filename in (
            ("bi", f"bi_demo_{index + 1:02d}.pdf"),
            ("contrato_assinado", f"contrato_demo_{index + 1:02d}.pdf"),
            ("certificado_habilitacoes", f"certificado_demo_{index + 1:02d}.pdf"),
        ):
            existing = db.query(CollaboratorDocument).filter(
                CollaboratorDocument.company_id == company.id,
                CollaboratorDocument.collaborator_id == user.id,
                CollaboratorDocument.doc_type == doc_type,
            ).first()
            if existing is None:
                db.add(CollaboratorDocument(
                    company_id=company.id,
                    collaborator_id=user.id,
                    filename=filename,
                    doc_type=doc_type,
                ))
    db.flush()


def _seed_business_data(db, company, accounts):
    _ensure_settings(db, company)
    cycles = [
        _ensure_cycle(db, company, "Ciclo 2025", False),
        _ensure_cycle(db, company, "Ciclo 2026", True),
    ]
    _seed_evaluations(db, company, accounts, cycles)
    _seed_leave(db, company, accounts)
    _seed_training(db, company, accounts)
    _seed_development(db, company, accounts)
    _seed_career_and_compensation(db, company, accounts)
    _seed_onboarding_and_corrections(db, company, accounts)
    _seed_dossier(db, company, accounts)
    _seed_survey_and_culture(db, company, accounts)
    _seed_notifications_and_chat(db, company, accounts)
    _seed_organ_and_disciplinary(db, company, accounts)
    _seed_talent(db, company, accounts, cycles[1])
    _seed_audit_and_documents(db, company, accounts)


def _summary(db, company):
    users = db.query(User).filter(User.company_id == company.id).order_by(User.id).all()
    counts = {}
    for user in users:
        role = user.role.value if hasattr(user.role, "value") else str(user.role)
        counts[role] = counts.get(role, 0) + 1
    required = (
        "employee_number",
        "admission_date",
        "contract_type",
        "job_category",
        "job_title",
        "department",
        "workplace",
        "nationality",
        "habilitacoes",
        "university",
        "course",
        "birth_date",
        "cv",
        "education",
        "experience",
        "certifications",
    )
    incomplete = []
    for user in users:
        profile = user.profile
        if profile is None or any(getattr(profile, field, None) in (None, "") for field in required):
            incomplete.append(user.email)
    print(f"Empresa: {company.name} (ID {company.id})")
    print(f"Utilizadores por perfil: {counts}")
    print(f"Fichas incompletas: {len(incomplete)}")
    if incomplete:
        print("Fichas para rever: " + ", ".join(incomplete))
    print("Dados de demonstração concluídos.")


def main():
    args = _parse_args()
    password = os.getenv("DEMO_PASSWORD")
    if not args.dry_run and not password:
        raise SystemExit("Defina DEMO_PASSWORD no ambiente antes de executar o seed.")
    if password and not 8 <= len(password) <= 72:
        raise SystemExit("DEMO_PASSWORD deve ter entre 8 e 72 caracteres.")
    if not args.dry_run and not args.confirm_demo:
        raise SystemExit("Use --confirm-demo para autorizar a inserção dos dados de demonstração.")
    Base.metadata.create_all(bind=engine)
    if not args.dry_run:
        ensure_schema_columns()
    db = SessionLocal()
    try:
        company = _find_company(db, args.company_id, args.company_name)
        if args.dry_run:
            print(f"Empresa encontrada: {company.name} (ID {company.id})")
            print("Perfis a criar: 20 colaboradores, 5 directores, 1 Capital Humano, 1 Comissão e 1 Administração.")
            return
        _fill_company(company)
        shifts = _ensure_shifts(db, company)
        password_hash = hash_password(password)
        accounts = []
        for spec in build_specs(args.include_platform_admin):
            user, _ = _upsert_user(db, company, spec, password_hash, not args.keep_existing_passwords)
            _populate_profile(db, user, company, spec, shifts)
            accounts.append((spec, user))
        db.flush()
        if not args.skip_business_data:
            _seed_business_data(db, company, accounts)
        db.commit()
        _summary(db, company)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
