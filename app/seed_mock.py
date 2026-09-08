"""
Seed de dados mock para teste geral.

Comportamento:
- Define a password de TODOS os utilizadores como "senha123456".
- Adiciona os perfis que faltam na empresa 1 (Comissão, Administração).
- Preenche fichas vazias e povoa os módulos de negócio (férias, chat,
  notificações, formação, avaliação, percurso, remuneração, ocupacional,
  dossier, cultura) com dados de demonstração para a empresa 1.

Idempotente: não apaga nada, só adiciona o que falta.

Executar a partir da raiz do projeto:
    .\\venv\\Scripts\\python.exe -m app.seed_mock
"""
import json
from datetime import date, datetime, time, timedelta, timezone

from app.core.database import Base, SessionLocal, engine
from app.core.security import hash_password

# Importar os modelos garante que as tabelas existem antes de inserir.
from app.models import (  # noqa: F401
    company, user, employee_profile, dossier, evaluation, disciplinary,
    training, development, survey, notification, occupational, compensation,
    career, culture_report, audit, onboarding, evaluation_settings,
    ficha_correction, leave, collaborator_document, shift, chat,
)
from app.models.company import Company
from app.models.user import User
from app.models.employee_profile import EmployeeProfile
from app.models.enums import (
    UserRole, ContractType, WorkScheduleType, DocumentType, SignatureType,
    EvaluationPhase, EvaluationCategory, TrainingSource, TrainingPlanStatus,
    TrainingActionStatus, DevelopmentPlanStatus, DevelopmentActionStatus,
    SurveyStatus, FitnessResult, CareerEventType, LeaveType, LeaveStatus,
)
from app.models.shift import Shift
from app.models.leave import LeaveRequest
from app.models.chat import ChatMessage
from app.models.notification import Notification
from app.models.training import TrainingPlan, TrainingAction
from app.models.development import DevelopmentPlan, DevelopmentAction
from app.models.evaluation import EvaluationCycle, Evaluation
from app.models.evaluation_settings import EvaluationSettings
from app.models.career import CareerEvent
from app.models.compensation import SalaryRecord, AttendanceRecord
from app.models.occupational import OccupationalExam
from app.models.dossier import Document, DocumentRead, Signature
from app.models.survey import Survey, SurveyResponse, SurveyParticipation
from app.models.onboarding import OnboardingItem


PASSWORD = "senha123456"
NOW = datetime.now(timezone.utc)
TODAY = date.today()
COMPANY1 = "NOSSA SEGUROS"

# Colaboradores da empresa 1 que já responderam ao pulse semeado.
PULSE_PARTICIPANTS_EMAILS = (
    "sergioamadeu@gmail.com", "afonsomario@gmail.com", "uimin@gmail.com",
    "colaborador@gmail.com", "nelves@gmail.com", "jelson@gmail.com",
    "jelso@gmail.com",
)
PULSE_TITLE = "Inquérito-pulso — 3.º Trimestre 2026"


def _commit(db):
    db.commit()


def _get_or_create_user(db, email, full_name, role, company_id):
    u = db.query(User).filter(User.company_id == company_id, User.email == email).first()
    if u is None:
        u = User(
            company_id=company_id,
            email=email,
            hashed_password=hash_password(PASSWORD),
            full_name=full_name,
            role=role,
            is_active=True,
            must_change_password=False,
        )
        db.add(u)
        db.flush()
    return u


def _next_employee_number(db, company_id):
    nums = [
        int(p.employee_number)
        for p in db.query(EmployeeProfile)
        .filter(EmployeeProfile.company_id == company_id)
        .all()
        if p.employee_number and p.employee_number.isdigit()
    ]
    return f"{(max(nums) + 1) if nums else 1:04d}"


def _profile(db, user_id, company_id):
    p = (
        db.query(EmployeeProfile)
        .filter(EmployeeProfile.user_id == user_id, EmployeeProfile.company_id == company_id)
        .first()
    )
    if p is None:
        p = EmployeeProfile(user_id=user_id, company_id=company_id)
        db.add(p)
        db.flush()
    return p


def reset_all_passwords(db):
    n = 0
    for u in db.query(User).all():
        u.hashed_password = hash_password(PASSWORD)
        u.must_change_password = False
        n += 1
    _commit(db)
    print(f"[1/10] Password de {n} utilizadores definida para '{PASSWORD}'.")


def seed_users_and_profiles(db, company):
    created = 0
    updates = 0

    # Perfis que faltam na empresa 1 (Comissão e Administração).
    extra = [
        ("comissao@nossaseguros.ao", "Maria Quissanga", UserRole.COMISSAO_AVALIACAO),
        ("administracao@nossaseguros.ao", "Adão Muanda", UserRole.ADMINISTRACAO),
    ]

    for email, name, role in extra:
        u = _get_or_create_user(db, email, name, role, company.id)
        num = _next_employee_number(db, company.id)
        p = _profile(db, u.id, company.id)
        if p.employee_number is None:
            p.employee_number = num
            p.admission_date = date(2022, 3, 10)
            p.contract_type = ContractType.EFETIVO
            p.job_title = "Membro da Comissão de Avaliação" if role == UserRole.COMISSAO_AVALIACAO else "Administração"
            p.department = "DCH — Avaliação" if role == UserRole.COMISSAO_AVALIACAO else "DCH — Administração"
            p.workplace = "Luanda — Sede"
            p.nationality = "Angolana"
            p.habilitacoes = "Licenciatura"
            p.university = "Universidade Agostinho Neto"
            p.course = "Gestão"
            p.education = [
                {"nivel": "Licenciatura", "ano_inicio": 2012, "ano_fim": 2016,
                 "pais": "Angola", "instituicao": "Universidade Agostinho Neto",
                 "curso": "Gestão", "areas": "Gestão, RH"}
            ]
            p.experience = [
                {"onde": "NOSSA SEGUROS", "ano_inicio": 2018, "ano_fim": None, "funcao": "Técnico de RH"}
            ]
            created += 1
        else:
            updates += 1

    # Preenche fichas vazias dos colaboradores existentes da empresa 1.
    fill = {
        3: ("Técnico de Vendas", "DCO — Vendas", "Angolana"),
        4: ("Assistente Administrativo", "DGA — Administração", "Angolana"),
        5: ("Chefe de Vendas", "DCO — Vendas", "Angolana"),
        6: ("Técnico de Sinistros", "DTO — Sinistros", "Angolana"),
        7: ("Analista Financeiro", "DFI — Finanças", "Angolana"),
        8: ("Director Comercial", "DCO — Direção", "Angolana"),
        9: ("Contabilista", "DFI — Contabilidade", "Angolana"),
        10: ("Técnico de Informática", "DTO — IT", "Angolana"),
        11: ("Assistente Comercial", "DCO — Vendas", "Angolana"),
    }
    for uid, (cargo, dept, nat) in fill.items():
        p = _profile(db, uid, company.id)
        if p.job_title is None or not p.job_title.strip():
            p.job_title = cargo
            p.department = dept
            p.workplace = "Luanda — Sede"
            p.nationality = nat
            p.admission_date = date(2019, 1, 15) if uid != 8 else date(2018, 6, 1)
            p.contract_type = ContractType.EFETIVO
            p.habilitacoes = "Licenciatura"
            p.university = "Universidade Metodista de Angola"
            p.course = "Gestão de Empresas"
            p.education = [
                {"nivel": "Licenciatura", "ano_inicio": 2010, "ano_fim": 2014,
                 "pais": "Angola", "instituicao": "Universidade Metodista de Angola",
                 "curso": p.course, "areas": "Gestão"}
            ]
            p.experience = [
                {"onde": "Empresa Anterior", "ano_inicio": 2014, "ano_fim": 2018, "funcao": "Técnico de área"},
                {"onde": "NOSSA SEGUROS", "ano_inicio": 2019, "ano_fim": None, "funcao": cargo},
            ]
            updates += 1

    _commit(db)
    print(f"[2/10] Perfis: {created} criados, {updates} preenchidos na empresa '{company.name}'.")


def seed_novo_colaborador(db, company):
    """Colaborador novo da empresa 1 que ainda NÃO respondeu ao pulse.

    Serve para testar o fluxo: entrar com esta conta, responder na aba Cultura
    e confirmar, do lado do Capital Humano, a resposta anónima (agregada) e o
    aumento da percentagem de participação.
    """
    email = "novocolaborador@gmail.com"
    existed = (
        db.query(User).filter(User.company_id == company.id, User.email == email).first()
        is not None
    )
    u = _get_or_create_user(db, email, "Pedro Zage", UserRole.COLABORADOR, company.id)
    p = _profile(db, u.id, company.id)
    if p.employee_number is None:
        p.employee_number = _next_employee_number(db, company.id)
    p.admission_date = date(2024, 3, 1)
    p.contract_type = ContractType.EFETIVO
    p.job_title = "Técnico de Sistemas"
    p.department = "DTO — TI"
    p.workplace = "Luanda — Sede"
    p.nationality = "Angolana"
    p.habilitacoes = "Licenciatura"
    p.university = "Instituto Superior de Tecnologias"
    p.course = "Engenharia Informática"
    p.education = [
        {"nivel": "Licenciatura", "ano_inicio": 2019, "ano_fim": 2023,
         "pais": "Angola", "instituicao": p.university,
         "curso": p.course, "areas": "Informática"}
    ]
    p.experience = [
        {"onde": "NOSSA SEGUROS", "ano_inicio": 2024, "ano_fim": None,
         "funcao": p.job_title},
    ]
    _commit(db)
    estado = "já existia; atualizado" if existed else "criado (ainda sem responder ao pulse)"
    print(f"[2/10] Novo colaborador '{email}' {estado}.")


def seed_shifts(db, company):
    if db.query(Shift).filter(Shift.company_id == company.id).count() > 0:
        print("[3/10] Turnos já existem; a saltar.")
        return
    shifts = [
        Shift(company_id=company.id, name="Manhã",
              start_time=time(8, 0), end_time=time(16, 0),
              break_start=time(12, 0), break_end=time(13, 0)),
        Shift(company_id=company.id, name="Tarde",
              start_time=time(14, 0), end_time=time(22, 0),
              break_start=time(18, 0), break_end=time(19, 0)),
        Shift(company_id=company.id, name="Noite",
              start_time=time(22, 0), end_time=time(6, 0),
              break_start=time(2, 0), break_end=time(3, 0)),
    ]
    db.add_all(shifts)
    db.flush()
    company.uses_shifts = True
    _commit(db)
    print(f"[3/10] {len(shifts)} turnos criados.")


def assign_fixed_schedule(db, company):
    for uid in (1, 2, 8, 7, 9):
        p = _profile(db, uid, company.id)
        if p.work_schedule_type is None:
            p.work_schedule_type = WorkScheduleType.FIXO
            p.fixed_entry_time = time(8, 0)
            p.fixed_exit_time = time(17, 0)
            p.fixed_break_start = time(12, 0)
            p.fixed_break_end = time(13, 0)
    # Dois colaboradores em regime de turno.
    shift_map = {s.name: s for s in db.query(Shift).filter(Shift.company_id == company.id).all()}
    for uid, sname in ((6, "Manhã"), (10, "Tarde")):
        p = _profile(db, uid, company.id)
        if p.work_schedule_type is None:
            p.work_schedule_type = WorkScheduleType.TURNO
            p.shift_id = shift_map[sname].id
    _commit(db)
    print("[4/10] Horários fixos e de turno atribuídos.")


def seed_leave(db, company):
    if db.query(LeaveRequest).filter(LeaveRequest.company_id == company.id).count() > 0:
        print("[5/10] Férias/ausências já existem; a saltar.")
        return

    d0 = TODAY
    rows = [
        # (collaborator, type, start, days, status, averbado, reason, rejection, doc)
        (5, LeaveType.FERIAS, d0 + timedelta(days=15), 12, LeaveStatus.PENDENTE_DIR, False,
         "Férias anuais — 2.ª quinzena", None, None),
        (7, LeaveType.FERIAS, d0 - timedelta(days=60), 10, LeaveStatus.APROVADA, True,
         "Férias anuais", None, None),
        (6, LeaveType.FERIAS, d0 - timedelta(days=75), 8, LeaveStatus.APROVADA, False,
         "Férias anuais — gozadas mas ainda por averbar", None, None),
        (9, LeaveType.FALTA, d0 - timedelta(days=20), 1, LeaveStatus.JUSTIFICADA, False,
         "Atestado médico", None, ("atestado_medico.pdf", "https://res.cloudinary.com/kamba/mock/falta_09.pdf")),
        (10, LeaveType.FERIAS, d0 - timedelta(days=40), 5, LeaveStatus.RECUSADA, False,
         "Pedido de férias fora do plano", "Período já atribuído a outro elemento da equipa.", None),
        (3, LeaveType.MATERNIDADE, d0 - timedelta(days=90), 90, LeaveStatus.APROVADA, False,
         "Licença de maternidade", None, ("declaracao_maternidade.pdf", "https://res.cloudinary.com/kamba/mock/maternidade_03.pdf")),
    ]
    for (cid, typ, start, days, status, averbado, reason, rej, doc) in rows:
        db.add(LeaveRequest(
            company_id=company.id, collaborator_id=cid, leave_type=typ,
            start_date=start, end_date=start + timedelta(days=days - 1), days=days,
            reason=reason, status=status, rejection_reason=rej, averbado=averbado,
            document_name=(doc[0] if doc else None), document_url=(doc[1] if doc else None),
        ))
    _commit(db)
    print(f"[5/10] {len(rows)} pedidos de férias/ausências criados (estados variados).")


def seed_notifications(db, company):
    if db.query(Notification).filter(Notification.company_id == company.id).count() > 0:
        print("[6/10] Notificações já existem; a saltar.")
        return
    notifs = [
        (8, "Nova autoavaliação submetida",
         "O colaborador Afonso Mario submeteu a autoavaliação do Ciclo 2026.",
         "avaliacao", "/avaliacao", False),
        (8, "Novo pedido de férias",
         "Afonso Mario pediu 12 dias de férias a partir de 25 de Setembro.",
         "ferias", "/ferias", False),
        (2, "Pedido de averbamento pendente",
         "uimin gozou férias que ainda não foram averbadas no mapa anual.",
         "ferias", "/ferias", False),
        (1, "Processo disciplinar arquivado",
         "O processo de Jelson de Oliveira foi arquivado sem medida.",
         "disciplina", "/disciplinar", True),
        (7, "Plano de formação aprovado",
         "O Plano de Formação 2026 foi aprovado pela Administração.",
         "formacao", "/formacao", False),
        (5, "Novo evento no percurso",
         "Foi registada uma promoção no seu percurso profissional.",
         "percurso", "/percurso", False),
    ]
    for (uid, title, msg, cat, link, read) in notifs:
        db.add(Notification(
            company_id=company.id, user_id=uid, title=title, message=msg,
            category=cat, link=link, is_read=read,
        ))
    _commit(db)
    print(f"[6/10] {len(notifs)} notificações criadas.")


def seed_chat(db, company):
    if db.query(ChatMessage).filter(ChatMessage.company_id == company.id).count() > 0:
        print("[7/10] Mensagens de chat já existem; a saltar.")
        return

    def conv(pairs):
        msgs = []
        for (sender, recipient, body, read, delta) in pairs:
            msgs.append(ChatMessage(
                company_id=company.id, sender_id=sender, recipient_id=recipient,
                body=body, is_read=read, created_at=(NOW - timedelta(hours=delta)),
            ))
        return msgs

    all_msgs = [
        # Afonso Rogerio (CH, 2) <-> Luis Soares (Director, 8)
        *conv([
            (2, 8, "Bom dia, Luis. O mapa de férias de Setembro já foi aprovado?", False, 30),
            (8, 2, "Bom dia! Sim, faltam só as férias do Afonso Mario para validar.", False, 28),
            (2, 8, "Obrigado, vou averbar assim que aprovares.", True, 26),
            (8, 2, "Aprovado. Podes aprovar o averbamento.", True, 2),
        ]),
        # colaborador (7) <-> Luis Soares (8)
        *conv([
            (7, 8, "Director, tenho uma dúvida sobre o processo de avaliação.", False, 20),
            (8, 7, "Claro. Recebeste a autoavaliação do Ciclo 2026?", True, 18),
            (7, 8, "Sim, vou submeter até sexta-feira.", True, 17),
        ]),
        # Jelson (10) <-> Heliecio (1)
        *conv([
            (10, 1, "Boa tarde, Heliecio. Peço desculpa pelo atraso no relatório.", True, 12),
            (1, 10, "Sem problema. Envia-me até ao fim do dia, por favor.", True, 11),
        ]),
    ]
    db.add_all(all_msgs)
    _commit(db)
    print(f"[7/10] {len(all_msgs)} mensagens de chat criadas (CH/Director/Colaborador).")


def seed_training_and_development(db, company):
    if db.query(TrainingPlan).filter(TrainingPlan.company_id == company.id).count() == 0:
        plan = TrainingPlan(company_id=company.id, name="Plano de Formação 2026",
                            status=TrainingPlanStatus.APROVADO)
        db.add(plan)
        db.flush()
        actions = [
            TrainingAction(company_id=company.id, plan_id=plan.id, collaborator_id=7,
                           title="Excel Avançado para Análise de Dados",
                           description="Formação prática em Excel para o financeiro.",
                           source=TrainingSource.SISTEMA, status=TrainingActionStatus.CONCLUIDA),
            TrainingAction(company_id=company.id, plan_id=plan.id, collaborator_id=9,
                           title="Comunicação Interpessoal",
                           description="Workshop de comunicação no atendimento interno.",
                           source=TrainingSource.AREA, status=TrainingActionStatus.APROVADA),
            TrainingAction(company_id=company.id, plan_id=plan.id, collaborator_id=10,
                           title="Segurança no Trabalho",
                           description="Formação obrigatória de segurança e saúde ocupacional.",
                           source=TrainingSource.SISTEMA, status=TrainingActionStatus.PROPOSTA),
            TrainingAction(company_id=company.id, plan_id=plan.id, collaborator_id=5,
                           title="Liderança de Equipas de Vendas",
                           description="Programa de liderança para chefes de equipa.",
                           source=TrainingSource.AREA, status=TrainingActionStatus.PROPOSTA),
        ]
        db.add_all(actions)
        print(f"[8/10] Plano de formação + {len(actions)} ações criadas.")
    else:
        print("[8/10] Plano de formação já existe; a saltar.")

    if db.query(DevelopmentPlan).filter(DevelopmentPlan.company_id == company.id).count() == 0:
        dp = DevelopmentPlan(company_id=company.id, collaborator_id=5, year=2026,
                             status=DevelopmentPlanStatus.ABERTO, created_by=2)
        db.add(dp)
        db.flush()
        db.add_all([
            DevelopmentAction(company_id=company.id, plan_id=dp.id,
                              title="Mentoria com a Administração",
                              description="Sessões quinzenais de mentoria.",
                              status=DevelopmentActionStatus.PENDENTE),
            DevelopmentAction(company_id=company.id, plan_id=dp.id,
                              title="Curso de Gestão Comercial",
                              status=DevelopmentActionStatus.CONCLUIDA),
        ])
        print("[8/10] PID (Plano Individual de Desenvolvimento) criado.")
    else:
        print("[8/10] PID já existe; a saltar.")
    _commit(db)


def seed_evaluations(db, company):
    if db.query(Evaluation).filter(Evaluation.company_id == company.id).count() > 0:
        print("[9/10] Avaliações já existem; a saltar.")
        return
    cycle = db.query(EvaluationCycle).filter(
        EvaluationCycle.company_id == company.id
    ).order_by(EvaluationCycle.id).first()
    if cycle is None:
        cycle = EvaluationCycle(company_id=company.id, name="Ciclo 2026", is_open=True)
        db.add(cycle)
        db.flush()

    director = db.query(User).filter(
        User.company_id == company.id, User.role == UserRole.DIRECTOR
    ).first()

    def goals(*items):
        return json.dumps([{"objetivo": g, "peso": 30 if i == 0 else (35 if i == 1 else 35)} for i, g in enumerate(items)])

    evals = [
        Evaluation(company_id=company.id, cycle_id=cycle.id, collaborator_id=7,
                   director_id=director.id, category=EvaluationCategory.TECNICO,
                   phase=EvaluationPhase.AUTOAVALIACAO,
                   defined_objectives=goals("Cumprir o report financeiro mensal", "Reduzir 10% de despesas", "Melhorar o fluxo de caixa")),
        Evaluation(company_id=company.id, cycle_id=cycle.id, collaborator_id=5,
                   director_id=director.id, category=EvaluationCategory.DIRIGENTE,
                   phase=EvaluationPhase.FECHADA, final_score=3.8, classification="Bom",
                   self_answers=json.dumps({"pontuacoes": [4, 4, 3]}),
                   director_answers=json.dumps({"pontuacoes": [4, 3.5, 4, 3.5, 3]}),
                   defined_objectives=goals("Aumentar vendas 20%", "Expandir a carteira de clientes", "Reduzir sinistralidade")),
        Evaluation(company_id=company.id, cycle_id=cycle.id, collaborator_id=10,
                   director_id=director.id, category=EvaluationCategory.TECNICO,
                   phase=EvaluationPhase.AVALIACAO_DIRECTOR,
                   defined_objectives=goals("Manter a infraestrutura de IT", "Automatizar 3 processos", "Suporte a 100% dos utilizadores")),
    ]
    db.add_all(evals)

    if db.query(EvaluationSettings).filter(
        EvaluationSettings.company_id == company.id
    ).count() == 0:
        db.add(EvaluationSettings(company_id=company.id, cycle_calendar="Janeiro a Dezembro"))
    _commit(db)
    print(f"[9/10] {len(evals)} avaliações criadas no ciclo '{cycle.name}' (3 fases distintas).")


def seed_career_and_comp(db, company):
    if db.query(CareerEvent).filter(CareerEvent.company_id == company.id).count() == 0:
        db.add_all([
            CareerEvent(company_id=company.id, collaborator_id=5, event_type=CareerEventType.LOUVOR,
                        event_date=date(2024, 5, 20), title="Louvor pelo desempenho em vendas",
                        description="Reconhecimento pela conquista do prémio trimestral."),
            CareerEvent(company_id=company.id, collaborator_id=5, event_type=CareerEventType.PROMOCAO,
                        event_date=date(2025, 11, 1), title="Promoção a Chefe de Vendas",
                        description="Progressão de carreira para chefia intermédia."),
            CareerEvent(company_id=company.id, collaborator_id=7, event_type=CareerEventType.NOMEACAO,
                        event_date=date(2025, 2, 10), title="Nomeação para comissão de orçamento",
                        description="Participação na comissão interna de orçamento."),
        ])
        print("[10/10] Percurso (louvores/nomeações/promoções) criado.")
    else:
        print("[10/10] Percurso já existe; a saltar.")

    if db.query(SalaryRecord).filter(SalaryRecord.company_id == company.id).count() == 0:
        db.add_all([
            SalaryRecord(company_id=company.id, collaborator_id=7, year=2024, gross_salary=480000, salary_grade="Técnico I"),
            SalaryRecord(company_id=company.id, collaborator_id=7, year=2025, gross_salary=520000, salary_grade="Técnico II"),
            SalaryRecord(company_id=company.id, collaborator_id=7, year=2026, gross_salary=560000, salary_grade="Técnico III"),
            SalaryRecord(company_id=company.id, collaborator_id=10, year=2025, gross_salary=300000, salary_grade="Júnior"),
            SalaryRecord(company_id=company.id, collaborator_id=10, year=2026, gross_salary=340000, salary_grade="Pleno"),
        ])
        print("[10/10] Progressão salarial criada.")
    else:
        print("[10/10] Progressão salarial já existe; a saltar.")

    if db.query(AttendanceRecord).filter(AttendanceRecord.company_id == company.id).count() == 0:
        db.add_all([
            AttendanceRecord(company_id=company.id, collaborator_id=7, period="2025", present_days=240,
                             justified_absences=4, unjustified_absences=1, vacation_days_taken=22),
            AttendanceRecord(company_id=company.id, collaborator_id=10, period="2025", present_days=236,
                             justified_absences=6, unjustified_absences=0, vacation_days_taken=20),
        ])
        print("[10/10] Assiduidade criada.")
    else:
        print("[10/10] Assiduidade já existe; a saltar.")

    if db.query(OccupationalExam).filter(OccupationalExam.company_id == company.id).count() == 0:
        db.add_all([
            OccupationalExam(company_id=company.id, collaborator_id=7, fitness=FitnessResult.APTO,
                             exam_date=date(2026, 2, 10), next_exam_date=date(2027, 2, 10)),
            OccupationalExam(company_id=company.id, collaborator_id=5, fitness=FitnessResult.APTO_COM_RESTRICOES,
                             exam_date=date(2026, 1, 20), next_exam_date=date(2026, 7, 20),
                             restriction_note="Restrição a trabalho noturno."),
            OccupationalExam(company_id=company.id, collaborator_id=10, fitness=FitnessResult.APTO,
                             exam_date=date(2025, 12, 1), next_exam_date=date(2026, 12, 1)),
        ])
        print("[10/10] Exames de medicina do trabalho criados.")
    else:
        print("[10/10] Exames de medicina do trabalho já existem; a saltar.")
    _commit(db)


def seed_dossier_and_survey(db, company):
    # Documentos do dossier (7 tipos) + leituras + assinaturas.
    if db.query(Document).filter(Document.company_id == company.id).count() == 0:
        docs = [
            Document(company_id=company.id, title="Contrato de Trabalho",
                     doc_type=DocumentType.CONTRATO,
                     content="Regula a relação laboral entre a empresa e o colaborador, conforme a Lei Geral do Trabalho."),
            Document(company_id=company.id, title="Regulamento Interno",
                     doc_type=DocumentType.REGULAMENTO_INTERNO,
                     content="Normas de funcionamento, ética e organização da empresa."),
            Document(company_id=company.id, title="Código de Ética",
                     doc_type=DocumentType.CODIGO_ETICA,
                     content="Princípios de conduta e integridade profissional."),
            Document(company_id=company.id, title="Política de Assiduidade",
                     doc_type=DocumentType.POLITICA_ASSIDUIDADE,
                     content="Regras de assiduidade, pontualidade e comunicação de faltas."),
            Document(company_id=company.id, title="Política de Remuneração",
                     doc_type=DocumentType.POLITICA_REMUNERACAO,
                     content="Enquadramento salarial e progressão de carreira."),
            Document(company_id=company.id, title="Regulamento de Avaliação",
                     doc_type=DocumentType.REGULAMENTO_AVALIACAO,
                     content="Regras do ciclo de avaliação de desempenho."),
            Document(company_id=company.id, title="Manual de Acolhimento",
                     doc_type=DocumentType.OUTRO,
                     content="Guia de integração de novos colaboradores."),
        ]
        db.add_all(docs)
        db.flush()
        for uid in (5, 7, 9, 10):
            for i in range(3):
                db.add(DocumentRead(company_id=company.id, document_id=docs[i].id, user_id=uid))
        print("[10/10] Documentos do dossier + leituras criadas.")
    else:
        print("[10/10] Documentos do dossier já existem; a saltar.")

    if db.query(Signature).filter(Signature.company_id == company.id).count() == 0:
        for uid in (5, 7, 9, 10):
            for st in SignatureType:
                db.add(Signature(company_id=company.id, user_id=uid, signature_type=st))
        print("[10/10] Assinaturas digitais criadas.")
    else:
        print("[10/10] Assinaturas digitais já existem; a saltar.")

    # Cultura organizacional: 1 inquérito com 6 respostas anónimas (>=5 revela resultados).
    if db.query(Survey).filter(Survey.company_id == company.id).count() == 0:
        survey = Survey(
            company_id=company.id,
            title="Inquérito-pulso — 3.º Trimestre 2026",
            dimensions=json.dumps(["confianca_lideranca", "clareza_estrategica",
                                   "reconhecimento", "equilibrio_vida"]),
            status=SurveyStatus.ABERTO,
        )
        db.add(survey)
        db.flush()
        for i in range(6):
            db.add(SurveyResponse(
                company_id=company.id, survey_id=survey.id,
                answers=json.dumps({
                    "confianca_lideranca": 3 + (i % 3),
                    "clareza_estrategica": 3 + ((i + 1) % 3),
                    "reconhecimento": 3 + ((i + 2) % 3),
                    "equilibrio_vida": 3 + ((i + 3) % 3),
                }),
            ))
        for uid in (3, 5, 6, 7, 9, 10):
            db.add(SurveyParticipation(company_id=company.id, survey_id=survey.id, user_id=uid))
        print("[10/10] Inquérito-pulso com 6 respostas anónimas criado.")
    else:
        print("[10/10] Inquéritos já existem; a saltar.")
    _resync_pulse_participations(db, company)
    _commit(db)


def _resync_pulse_participations(db, company):
    """Liga as participações do pulse semeado da empresa 1 aos utilizadores atuais.

    Execuções anteriores gravaram SurveyParticipation com user_ids que já não
    correspondem aos colaboradores (registos 'soltos'), ou em pulses criados à
    mão na UI. Esta passagem idempotente:
      - apaga participações de qualquer pulse que não seja o semeado
        (artefactos de execuções anteriores);
      - no pulse semeado, garante os participantes pretendidos SEM apagar os
        registos legítimos criados através da app (ex.: resposta dada na UI).
    """
    if company.name != COMPANY1:
        return
    pulses = (
        db.query(Survey)
        .filter(Survey.company_id == company.id)
        .all()
    )
    if not pulses:
        return
    seed_survey = next((s for s in pulses if s.title == PULSE_TITLE), None)
    if seed_survey is None:
        return
    intended = [
        u.id for u in db.query(User)
        .filter(User.company_id == company.id, User.email.in_(PULSE_PARTICIPANTS_EMAILS))
        .all()
    ]
    for s in pulses:
        if s.id == seed_survey.id:
            continue
        for r in (
            db.query(SurveyParticipation)
            .filter(SurveyParticipation.survey_id == s.id)
            .all()
        ):
            db.delete(r)
    for uid in intended:
        exists = (
            db.query(SurveyParticipation)
            .filter(
                SurveyParticipation.survey_id == seed_survey.id,
                SurveyParticipation.user_id == uid,
            )
            .first()
        )
        if exists is None:
            db.add(SurveyParticipation(
                company_id=company.id, survey_id=seed_survey.id, user_id=uid
            ))
    print(f"[10/10] Participações do pulse resincronizadas ({len(intended)} utilizadores).")


def summary(db):
    c2 = db.query(Company).filter(Company.id == 2).first()
    print("\n===== RESUMO =====")
    print(f"Empresa 1: '{COMPANY1}' — users ativos:")
    for u in db.query(User).filter(User.company_id == 1, User.is_active == True).order_by(User.id):  # noqa: E712
        print(f"   {u.email:38s} {u.full_name:25s} {u.role.value}")
    if c2:
        print(f"Empresa 2: '{c2.name}' — users ativos:")
        for u in db.query(User).filter(User.company_id == 2, User.is_active == True).order_by(User.id):  # noqa: E712
            print(f"   {u.email:38s} {u.full_name:25s} {u.role.value}")
    print(f"\nTODOS com a password: {PASSWORD}")
    print(f"Total users na BD: {db.query(User).count()}")


def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        company = db.query(Company).filter(Company.name == COMPANY1).first()
        if company is None:
            company = Company(name=COMPANY1, plan="essencial", is_active=True)
            db.add(company)
            db.flush()

        reset_all_passwords(db)
        seed_users_and_profiles(db, company)
        seed_novo_colaborador(db, company)
        seed_shifts(db, company)
        assign_fixed_schedule(db, company)
        seed_leave(db, company)
        seed_notifications(db, company)
        seed_chat(db, company)
        seed_training_and_development(db, company)
        seed_evaluations(db, company)
        seed_career_and_comp(db, company)
        seed_dossier_and_survey(db, company)
        summary(db)
        print("\nSeed concluído.")
    finally:
        db.close()


if __name__ == "__main__":
    main()