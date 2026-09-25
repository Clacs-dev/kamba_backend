"""
Seed profundo de dados de demonstração — complemento do `seed_demo.py`.

O `seed_demo.py` cria a empresa, as contas e uma primeira camada de dados.
Este script semeia a **segunda camada**: dados ricos e coerentes entre
módulos, gravados no formato exacto que a aplicação usa, para que os ecrãs
apareçam "cheios" e credíveis (dossiês, relatórios, gráfico de avaliação,
9-Box, plano de formação, processos disciplinares em todas as fases, etc.).

Princípios:
- **Aditivo e idempotente**: nunca apaga nem sobrescreve dados existentes;
  cada inserção é precedida de verificação pela chave natural. Pode correr
  vezes seguidas sem duplicar nada.
- **Não cria utilizadores**: usa as contas já existentes na empresa (as do
  `seed_demo.py`). Se a empresa não tiver contas, falha com uma mensagem
  clara a dizer para correr primeiro o `seed_demo.py`.
- **Formato fiel**: as respostas de avaliação são gravadas no contrato real
  (`objectives`/`competencies`/`values`) e as pontuações são calculadas pelo
  próprio motor da aplicação (`compute_score`) — nunca escritas à mão. Assim,
  qualquer recálculo da plataforma devolve o mesmo valor.
- **Determinista**: gerador pseudo-aleatório com semente fixa, para que duas
  execuções produzam exatamente o mesmo conjunto de dados.

Uso:
    python -m app.seed_deep --company-name "Minha Empresa" --dry-run
    DEMO_PASSWORD=... python -m app.seed_deep --company-name "Minha Empresa" --confirm-demo
"""
import argparse
import json
import os
import random
from datetime import date, datetime, timedelta, timezone

from app.api.routes.evaluation_settings import get_or_create_settings
from app.core.database import Base, SessionLocal, engine
from app.core.schema_migrations import ensure_schema_columns
from app.models.audit import AuditEvent
from app.models.career import CareerEvent
from app.models.chat import ChatMessage
from app.models.company import Company
from app.models.compensation import AttendanceRecord, SalaryRecord
from app.models.culture_report import CultureReport
from app.models.development import DevelopmentAction, DevelopmentPlan
from app.models.disciplinary import DisciplinaryCommitteeMember, DisciplinaryProcess
from app.models.dossier import Document, DocumentRead
from app.models.enums import (
    CareerEventType,
    CommitteeRole,
    DevelopmentActionStatus,
    DevelopmentPlanStatus,
    DisciplinaryOutcome,
    DisciplinaryPhase,
    EvaluationCategory,
    EvaluationPhase,
    LeaveStatus,
    LeaveType,
    PotentialLevel,
    ReadinessLevel,
    SurveyStatus,
    TrainingActionStatus,
    TrainingPlanStatus,
    TrainingSource,
    UserRole,
)
from app.models.evaluation import Evaluation, EvaluationCycle
from app.models.leave import LeaveRequest
from app.models.notification import Notification
from app.models.organ import OrganMember
from app.models.survey import Survey, SurveyParticipation, SurveyResponse
from app.models.talent import SuccessionPlan, TalentMatrix
from app.models.training import TrainingAction, TrainingPlan
from app.models.user import User
from app.schemas.evaluation import DEFAULT_FORM_CONFIG
from app.services.evaluation_scoring import compute_score

RNG = random.Random(20260925)
TODAY = date.today()
NOW = datetime.now(timezone.utc)

# Prefixo das chaves naturais criadas por este seed (títulos, referências).
PREFIXO = "KAMBA-DEMO"

COMPETENCIAS = [
    "orientacao_resultados",
    "trabalho_equipa",
    "etica_conformidade",
    "comunicacao",
    "adaptabilidade",
]
VALORES = ["codigo_etica", "seguranca_saude", "assiduidade_pontualidade"]

# Objetivos pactuados por direcção (os pesos somam 100).
OBJETIVOS_POR_DIRECAO = {
    "DCO — Vendas": [
        ("Atingir 100% da meta anual de vendas da equipa", 40),
        ("Reduzir o prazo médio de recebimento da carteira para 60 dias", 30),
        ("Garantir a adopção do CRM por 90% da equipa comercial", 30),
    ],
    "DCO — Seguros": [
        ("Aumentar a carteira de seguros de vida em 15%", 40),
        ("Reduzir a sinistralidade da frota em 8%", 35),
        ("Certificar 100% da equipa em produto e legislação", 25),
    ],
    "DTO — Sinistros": [
        ("Reduzir o prazo médio de regularização de sinistros para 45 dias", 40),
        ("Recuperar 70% do valor recuperável em negociação com a seguradora", 30),
        ("Reduzir a reincidência de sinistros complexos", 30),
    ],
    "DGA — Administração Geral": [
        ("Digitalizar 100% do arquivo corrente", 40),
        ("Reduzir o tempo médio de resposta a requerimentos internos", 30),
        ("Garantir o cumprimento dos prazos legais de arquivo", 30),
    ],
    "DGA — Riscos": [
        ("Concluir o mapa de riscos da empresa", 40),
        ("Implementar 100% das acções de mitigação prioritárias", 35),
        ("Reduzir em 20% os sinistros de responsabilidade civil", 25),
    ],
    "DGA — Conformidade": [
        ("Assegurar 100% de conformidade com o regime de seguros", 40),
        ("Concluir a revisão dos contratos de distribuição", 35),
        ("Reduzir a zero as não conformidades críticas", 25),
    ],
    "DSI — Sistemas de Informação": [
        ("Assegurar disponibilidade da plataforma KAMBA acima de 99,5%", 40),
        ("Concluir a migração dos módulos de sinistros e formação", 30),
        ("Reduzir o tempo médio de resolução de incidentes para 4 horas", 30),
    ],
    "DFI — Finanças": [
        ("Entregar o orçamento e o balanço dentro do prazo legal", 40),
        ("Reduzir o período médio de recebimento a 60 dias", 35),
        ("Automatizar 80% da reconciliação bancária", 25),
    ],
    "DCH — Capital Humano": [
        ("Concluir 100% das avaliações de desempenho do ciclo", 40),
        ("Reduzir o tempo médio de recrutamento para 35 dias", 30),
        ("Aumentar a participação dos pulsos de cultura para 80%", 30),
    ],
    "DSO — Segurança": [
        ("Concluir 100% das visitas de segurança programadas", 40),
        ("Reduzir em 30% os acidentes de trabalho com baixa", 35),
        ("Realizar dois simulacros de evacuação", 25),
    ],
    "DCO — Marketing": [
        ("Aumentar em 25% a presença digital da marca", 40),
        ("Gerar 200 novos contactos comerciais qualificados", 35),
        ("Reduzir a um terço o custo por contacto", 25),
    ],
}
OBJETIVOS_GERAIS = [
    ("Cumprir os resultados globais da empresa", 40),
    ("Melhorar a qualidade do serviço ao cliente", 35),
    ("Partilhar conhecimento com a equipa", 25),
]

IDIOMAS_BASE = [
    {"nome": "Português", "fala": "Nativo", "escreve": "Nativo", "le": "Nativo"},
    {"nome": "Kimbundu", "fala": "Bom", "escreve": "Básico", "le": "Bom"},
    {"nome": "Inglês", "fala": "Intermédio", "escreve": "Intermédio", "le": "Intermédio"},
    {"nome": "Francês", "fala": "Básico", "escreve": "Básico", "le": "Iniciante"},
]

APTIDOES_SOCIAIS = [
    "Comunicação clara e empática; trabalho em equipa; adaptabilidade; responsabilidade; iniciativa.",
    "Liderança de equipas; comunicação assertiva; gestão de conflitos; orientação para o cliente.",
    "Rigor e atenção ao detalhe; capacidade de negociação; autonomia e sentido crítico.",
    "Escuta ativa; capacidade de improviso; respeito pela diversidade e pelos colegas.",
    "Organização e planeamento; persistência; capacidade de aprendizagem contínua.",
]

APTIDOES_TECNICAS = [
    "Excel avançado; CRM; análise de indicadores de gestão.",
    "Regulamentação de seguros; processamento de sinistros; registo de averbações.",
    "Contabilidade geral; fiscalidade; reconciliação bancária.",
    "Administração de sistemas; redes; suporte a utilizadores.",
    "Análise de dados; Power BI; bases de dados SQL.",
    "Gestão documental; digitalização de arquivo; Lotus Notes e KAMBA.",
]

BAIRROS = [
    "Rua Comandante Gika, Ingombota, Luanda",
    "Avenida 4 de Fevereiro, Maianga, Luanda",
    "Rua Rainha Ginga, Rangel, Luanda",
    "Avenida Deolinda Rodrigues, Talatona, Luanda",
    "Rua Amilcar Cabral, Viana, Luanda",
    "Rua do Kikolo, Talatona, Luanda",
    "Rua São Paulo, Miramar, Luanda",
    "Bairro do Roque Santeiro, Luanda",
]

# -----------------------------------------------------------------------------


class Relatorio:
    """Conta o que foi criado e o que já existia, por módulo."""

    def __init__(self):
        self.linhas = []

    def add(self, modulo, criados, existentes):
        self.linhas.append((modulo, criados, existentes))

    def resumo(self):
        """Resumo numa linha: 'criados X, ja existia Y'."""
        criados = sum(c for _, c, _ in self.linhas)
        existentes = sum(e for _, _, e in self.linhas)
        return f"{criados} criado(s), {existentes} registo(s) intacto(s) em {len(self.linhas)} modulos"

    def imprimir(self):
        print()
        print(f"{'modulo':<34}{'criados':>10}{'ja existia':>14}")
        print("-" * 58)
        for modulo, criados, existentes in self.linhas:
            print(f"{modulo:<34}{criados:>10}{existentes:>14}")
        total_c = sum(c for _, c, _ in self.linhas)
        total_e = sum(e for _, _, e in self.linhas)
        print("-" * 58)
        print(f"{'TOTAL':<34}{total_c:>10}{total_e:>14}")


def _parse_args():
    parser = argparse.ArgumentParser(
        description="Semeia dados de demonstração profundos e coerentes numa empresa KAMBA"
    )
    alvo = parser.add_mutually_exclusive_group(required=True)
    alvo.add_argument("--company-id", type=int)
    alvo.add_argument("--company-name")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--confirm-demo", action="store_true")
    return parser.parse_args()


def _find_company(db, company_id=None, company_name=None):
    if company_id is not None:
        company = db.query(Company).filter(Company.id == company_id).first()
        if company is None:
            raise SystemExit(f"Empresa com ID {company_id} nao existe.")
        return company
    company = (
        db.query(Company)
        .filter(Company.name.ilike(f"%{company_name}%"))
        .order_by(Company.id)
        .first()
    )
    if company is None:
        raise SystemExit(f"Nenhuma empresa corresponde a '{company_name}'.")
    return company


def _contas(db, company):
    """Devolve (colaboradores, directores, capitao_humano, comissao, administracao)."""
    users = (
        db.query(User)
        .filter(User.company_id == company.id)
        .order_by(User.id)
        .all()
    )
    if not users:
        raise ValueError(
            "A empresa nao tem utilizadores. Corra primeiro o seed_demo.py "
            "(python -m app.seed_demo --company-name ... --confirm-demo)."
        )
    colaboradores = [u for u in users if u.role == UserRole.COLABORADOR]
    directores = [u for u in users if u.role == UserRole.DIRECTOR]
    if not colaboradores or not directores:
        raise ValueError(
            "A empresa precisa de colaboradores e de directores para semear este "
            "nivel de dados. Defina DEEP_SEED_PASSWORD para a semente completar "
            "as contas, ou corra primeiro o seed_demo.py."
        )
    def primeiro(role):
        return next((u for u in users if u.role == role), None)
    return colaboradores, directores, primeiro(UserRole.CAPITAL_HUMANO), primeiro(
        UserRole.COMISSAO_AVALIACAO
    ), primeiro(UserRole.ADMINISTRACAO)


def _garantir_contas(db, company, password, completar=False):
    """
    Cria as contas e perfis de demo (reaproveitando o seed_demo) quando a empresa
    ainda nao tem utilizadores. Com `completar`, preenche tambem as contas em
    falta de uma empresa que ja tenha SOME utilizadores (ex.: um unico
    colaborador criado a mao). Devolve True quando criou alguma coisa.
    """
    if not password:
        return False
    da_empresa = db.query(User).filter(User.company_id == company.id).all()
    if da_empresa and not (
        completar
        and not any(u.role == UserRole.DIRECTOR for u in da_empresa)
    ):
        return False
    from app import seed_demo

    print(f"[semente] A completar as contas de demo de '{company.name}'.")
    seed_demo.semear_empresa(db, company, password)
    db.flush()
    return True


def _perfil(user):
    if user.profile is None:
        raise ValueError(
            f"O utilizador {user.email} nao tem ficha. Corra primeiro o seed_demo.py."
        )
    return user.profile


def _director_de(directores, colaborador):
    """
    Escolhe o director que avalia `colaborador`: o da mesma direcao e, quando o
    proprio colaborador e' director, nunca ele mesmo (avaliado por um par).
    """
    perfil = _perfil(colaborador)
    for director in directores:
        if director.id == colaborador.id:
            continue
        if _perfil(director).department == perfil.department:
            return director
    for director in directores:
        if director.id != colaborador.id:
            return director
    return directores[0]


def _notificar(db, company, user, title, message, category, link, is_read=False, dias=0):
    """Cria uma notificação se ainda não existir uma com o mesmo título para o utilizador."""
    if user is None:
        return False
    existente = (
        db.query(Notification)
        .filter(
            Notification.company_id == company.id,
            Notification.user_id == user.id,
            Notification.title == title,
        )
        .first()
    )
    if existente is not None:
        return False
    db.add(Notification(
        company_id=company.id,
        user_id=user.id,
        title=title,
        message=message,
        category=category,
        link=link,
        is_read=is_read,
        created_at=NOW - timedelta(days=dias, hours=RNG.randint(0, 8)),
    ))
    return True


def _auditar(db, company, actor, action, detail, dias=0):
    existente = (
        db.query(AuditEvent)
        .filter(
            AuditEvent.company_id == company.id,
            AuditEvent.action == action,
            AuditEvent.detail == detail,
        )
        .first()
    )
    if existente is not None:
        return False
    db.add(AuditEvent(
        company_id=company.id,
        actor_id=actor.id if actor else None,
        actor_name=actor.full_name if actor else "Sistema",
        actor_role=actor.role.value if actor else "sistema",
        action=action,
        detail=detail,
        created_at=NOW - timedelta(days=dias, hours=RNG.randint(0, 8)),
    ))
    return True


# ------------------------------------------------------------------ 1. FICHAS


def _semear_fichas(db, company, colaboradores, relatorio):
    """Preenche morada, telefone, idiomas, aptidoes e certificationes de cada ficha."""
    criados = 0
    existentes = 0
    for indice, user in enumerate(colaboradores):
        perfil = _perfil(user)
        mudou = False
        if not perfil.address:
            perfil.address = BAIRROS[indice % len(BAIRROS)]
            mudou = True
        if not perfil.phone:
            perfil.phone = f"+244 9{RNG.randint(10, 99)} {RNG.randint(100, 999)} {RNG.randint(100, 999)}"
            mudou = True
        if not perfil.languages:
            perfil.languages = [dict(idioma) for idioma in IDIOMAS_BASE[: 2 + indice % 3]]
            mudou = True
        if not perfil.social_skills:
            perfil.social_skills = APTIDOES_SOCIAIS[indice % len(APTIDOES_SOCIAIS)]
            mudou = True
        if not perfil.technical_skills:
            perfil.technical_skills = APTIDOES_TECNICAS[indice % len(APTIDOES_TECNICAS)]
            mudou = True

        # Certificacoes: acrescenta duas a mais as que ja existam, sem as remover.
        certificacoes = list(perfil.certifications or [])
        extra = [
            {
                "nome": "Seguracao da informacao e proteccao de dados",
                "instituicao": "KAMBA Academy",
                "data": str(TODAY.year - (indice % 2)),
                "certificado_url": None,
                "validade": str(TODAY.year + 2),
            },
            {
                "nome": "Primeiros socorros no trabalho",
                "instituicao": "Cruz Vermelha de Angola",
                "data": str(TODAY.year - 1 - (indice % 3)),
                "certificado_url": None,
                "validade": str(TODAY.year + 1),
            },
        ]
        nomes = {str(c.get("nome")) for c in certificacoes}
        for certificado in extra:
            if certificado["nome"] not in nomes:
                certificacoes.append(certificado)
                mudou = True
        perfil.certifications = certificacoes

        # Formacao: acrescenta uma segunda HVAC quando so existe uma.
        formacao = list(perfil.education or [])
        if len(formacao) < 2:
            inicio = 2003 + (indice % 6)
            formacao.append({
                "nivel": "Ensino Medio",
                "ano_inicio": inicio,
                "ano_fim": inicio + 3,
                "pais": "Angola",
                "instituicao": "Liceu Salvador Correia",
                "curso": "Ciências económicas e de gestão",
                "areas": "Economia, gestão e contabilidade",
            })
            mudou = True
        perfil.education = formacao

        if mudou:
            criados += 1
        else:
            existentes += 1
    db.flush()
    relatorio.add("fichas (morada/idiomas/aptidoes)", criados, existentes)


# ------------------------------------------------------------------ 2. CICLOS


def _garantir_ciclo(db, company, nome, is_open):
    ciclo = (
        db.query(EvaluationCycle)
        .filter(EvaluationCycle.company_id == company.id, EvaluationCycle.name == nome)
        .first()
    )
    if ciclo is None:
        ciclo = EvaluationCycle(
            company_id=company.id, name=nome, is_open=is_open,
            form_config=json.loads(json.dumps(DEFAULT_FORM_CONFIG)),
        )
        db.add(ciclo)
        db.flush()
        return ciclo, True
    mudou = False
    if is_open is not None and ciclo.is_open != is_open:
        ciclo.is_open = is_open
        mudou = True
    if not ciclo.form_config:
        ciclo.form_config = json.loads(json.dumps(DEFAULT_FORM_CONFIG))
        mudou = True
    db.flush()
    return ciclo, mudou


def _semear_ciclos(db, company, relatorio):
    """Garante tres ciclos (2024, 2025, 2026) com o formulario configurado."""
    definicoes = [
        (f"Ciclo {TODAY.year - 2}", False),
        (f"Ciclo {TODAY.year - 1}", False),
        (f"Ciclo {TODAY.year}", True),
    ]
    ciclos = {}
    criados = 0
    existentes = 0
    for nome, is_open in definicoes:
        ciclo, mudou = _garantir_ciclo(db, company, nome, is_open)
        ciclos[nome] = ciclo
        criados += 1 if mudou else 0
        existentes += 0 if mudou else 1
    db.flush()
    relatorio.add("ciclos de avaliacao", criados, existentes)
    return ciclos


# -------------------------------------------------------------- 3. AVALIACOES


def _objetivos_de(perfil, seed):
    """Objectivos pactuados no inicio do ciclo, em JSON no contrato da aplicacao."""
    pares = OBJETIVOS_POR_DIRECAO.get(perfil.department or "", OBJETIVOS_GERAIS)
    if seed % 4 == 3:
        # Um em cada quatro colaboradores tem objectivos proprios (pactuados
        # individualmente com a chefia) em vez dos da direccao.
        pares = [
            ("Reduzir o tempo de ciclo da sua area em 20%", 40),
            ("Automatizar uma tarefa repetitiva do seu posto", 35),
            ("Formar um colega da equipa em SST", 25),
        ]
    return json.dumps(
        [{"description": descricao, "weight": peso} for descricao, peso in pares],
        ensure_ascii=False,
    )


def _respostas(perfil, nivel, seed, director=False):
    """
    Monta as respostas no contrato real da aplicacao.

    nivel: 0.0 (muito fraco) .. 1.0 (excelente). O director avalia a execucao dos
    objectivos; o colaborador avalia a sua propria performance, que costuma ser
    ligeiramente mais otimista (ou maisSevera, em casos de conflito com a chefia).
    """
    objetivos = _objetivos_de(perfil, seed)
    lista = json.loads(objetivos)
    # O objectivo com maior peso e' o que o director acompanha de perto.
    if director:
        base_execucao = 45 + nivel * 55
        desvio = RNG.uniform(-8, 6)
    else:
        base_execucao = 50 + nivel * 52
        desvio = RNG.uniform(-5, 10)
    respostas_obj = []
    for indice, item in enumerate(lista):
        # Objectivos de menor peso costumam ter execucao mais irregular.
        penalidade = 6 * indice
        execucao = max(0, min(100, base_execucao + desvio - penalidade + RNG.uniform(-7, 7)))
        respostas_obj.append({
            "description": item["description"],
            "weight": item["weight"],
            "execution": round(execucao),
        })

    competencias = {}
    for chave in COMPETENCIAS:
        # A competencia etica acompanha o nivel global com menos variacao.
        if chave == "etica_conformidade":
            competencias[chave] = max(1, min(5, round(2 + nivel * 3)))
        else:
            competencias[chave] = max(1, min(5, round(1.5 + nivel * 3.4 + RNG.uniform(-0.4, 0.4))))
    valores = {chave: (nivel >= 0.45 or RNG.random() < 0.6) for chave in VALORES}
    return json.dumps(
        {"objectives": respostas_obj, "competencies": competencias, "values": valores},
        ensure_ascii=False,
    )


def _comentario(nivel, fase, nome):
    if fase == EvaluationPhase.CONCORDANCIA and nivel < 0.4:
        return (
            f"O colaborador {nome} considera os resultados obtidos insuficientes e "
            "solicita a revisao dos criterios avaliados, por nao ter sido ponderada a "
            "reorganizacao do trabalho a que foi sujeito no segundo semestre."
        )
    if nivel >= 0.85:
        return (
            "Desempenho excelente. Resultados muito acima da meta, com contribuicao "
            "relevante para a melhoria dos processos da area e apoio concreto a colegas."
        )
    if nivel >= 0.65:
        return (
            "Cumpriu os objectivos pactuados, com participacao activa nas actividades "
            "da equipa. Ha margem para assumir responsabilidades de maior complexidade."
        )
    if nivel >= 0.45:
        return (
            "Desempenho conforme o esperado: cumpre as responsabilidades acordadas, mas "
            "a execucao de alguns objectivos ficou abaixo da meta e a comunicacao "
            "interna precisa de mais estrutura."
        )
    if nivel >= 0.25:
        return (
            "Execucao abaixo do esperado em parte dos objectivos, com varias faltas "
            "injustificadas e dificuldade em cumprir prazos apos ser alertado pela chefia."
        )
    return (
        "Desempenho claramente insuficiente. Nao se verificou a execucao dos objectivos "
        "pactuados, com incumprimentos repetidos de prazos e procedimento disciplinar "
        "em curso."
    )


def _semear_avaliacoes(db, company, colaboradores, directores, ciclos, relatorio):
    """
    Cria avaliacoes em todas as fases do ciclo, com respostas no contrato real e
    pontuacao calculada por `compute_score` (a mesma funcao da aplicacao).
    """
    settings = get_or_create_settings(db, company.id)
    ano_atual = TODAY.year
    fases_2026 = [
        EvaluationPhase.AUTOAVALIACAO,
        EvaluationPhase.AVALIACAO_DIRECTOR,
        EvaluationPhase.AVALIACAO_DIRECTOR,
        EvaluationPhase.CONCORDANCIA,
        EvaluationPhase.CONCORDANCIA,
        EvaluationPhase.COMISSAO,
        EvaluationPhase.COMISSAO,
        EvaluationPhase.FECHADA,
        EvaluationPhase.FECHADA,
        EvaluationPhase.VALIDADA,
        EvaluationPhase.VALIDADA,
        EvaluationPhase.VALIDADA,
    ]
    criados = 0
    existentes = 0
    # Tambem os directores sao avaliados (categoria DIRIGENTE, com ponderacoes
    # diferentes), tal como o seed_demo ja fazia.
    alvos = [(user, EvaluationCategory.TECNICO) for user in colaboradores]
    alvos += [(user, EvaluationCategory.DIRIGENTE) for user in directores]
    for indice, (user, categoria) in enumerate(alvos):
        perfil = _perfil(user)
        director = _director_de(directores, user)
        pesos = (
            {"objectives": settings.tec_objectives, "competencies": settings.tec_competencies, "values": settings.tec_values}
            if categoria == EvaluationCategory.TECNICO
            else {"objectives": settings.dir_objectives, "competencies": settings.dir_competencies, "values": settings.dir_values}
        )
        # Perfil de desempenho: cresce com a senioridade e varia por pessoa.
        nivel_base = 0.25 + ((indice * 7) % 10) / 14.0

        for deslocamento, (nome_ciclo, ciclo) in enumerate(sorted(ciclos.items())):
            ano = int(nome_ciclo.split()[-1])
            if ano == ano_atual:
                fase = fases_2026[indice % len(fases_2026)]
                nivel = max(0.05, min(0.98, nivel_base + RNG.uniform(-0.12, 0.12)))
            elif ano == ano_atual - 1:
                fase = EvaluationPhase.VALIDADA if indice % 5 else EvaluationPhase.FECHADA
                nivel = max(0.05, min(0.98, nivel_base + RNG.uniform(-0.18, 0.06)))
            else:
                fase = EvaluationPhase.VALIDADA
                nivel = max(0.05, min(0.95, nivel_base + RNG.uniform(-0.25, 0.0)))

            avaliacao = (
                db.query(Evaluation)
                .filter(
                    Evaluation.cycle_id == ciclo.id,
                    Evaluation.collaborator_id == user.id,
                )
                .first()
            )
            respostas_director = _respostas(perfil, nivel, indice, director=True)
            nota, classificacao = compute_score(
                json.loads(respostas_director), categoria, weights=pesos
            )
            concluida = fase in (EvaluationPhase.FECHADA, EvaluationPhase.VALIDADA)
            if avaliacao is None:
                avaliacao = Evaluation(
                    company_id=company.id,
                    cycle_id=ciclo.id,
                    collaborator_id=user.id,
                    director_id=director.id,
                    category=categoria,
                    phase=fase,
                    self_answers=_respostas(perfil, min(1.0, nivel + 0.1), indice),
                    director_answers=respostas_director,
                    final_score=nota if concluida else None,
                    classification=classificacao if concluida else None,
                    appeal_reason=None,
                    appeal_deadline=None,
                    cycle_adjusted=(indice % 11 == 0),
                    commission_decision=None,
                    defined_objectives=_objetivos_de(perfil, indice),
                )
                if fase == EvaluationPhase.COMISSAO:
                    avaliacao.appeal_reason = _comentario(
                        min(0.45, nivel), EvaluationPhase.CONCORDANCIA, user.full_name
                    )
                    avaliacao.appeal_deadline = NOW + timedelta(days=RNG.randint(-3, 6))
                if fase == EvaluationPhase.VALIDADA and indice % 7 == 0:
                    avaliacao.commission_decision = (
                        "Recurso julgado procedente parcial: a comissao ajustou a nota de "
                        "competencias em +0,3 e manteve a pontuacao final."
                    )
                db.add(avaliacao)
                criados += 1
                continue

            # Avaliacao ja existente (do seed_demo): reescreve apenas se estiver
            # no formato antigo, para o ecra mostrar os blocos reais.
            legada = False
            if avaliacao.defined_objectives:
                try:
                    primeiro = json.loads(avaliacao.defined_objectives)[0]
                    legada = "objetivo" in primeiro or "description" not in primeiro
                except Exception:
                    legada = True
            if not legada and avaliacao.director_answers:
                try:
                    legada = "objectives" not in json.loads(avaliacao.director_answers)
                except Exception:
                    legada = True
            if legada:
                # Normaliza a avaliacao existente: respostas no contrato real,
                # objectivos pactuados correctos e fase coerente com a nota
                # (uma avaliacao por decidir nao tem pontuacao final).
                avaliacao.defined_objectives = _objetivos_de(perfil, indice)
                avaliacao.self_answers = _respostas(perfil, min(1.0, nivel + 0.1), indice)
                avaliacao.director_answers = respostas_director
                avaliacao.phase = fase
                if concluida:
                    avaliacao.final_score = nota
                    avaliacao.classification = classificacao
                else:
                    avaliacao.final_score = None
                    avaliacao.classification = None
                if fase != EvaluationPhase.COMISSAO:
                    avaliacao.appeal_reason = None
                    avaliacao.appeal_deadline = None
                existentes += 1
            else:
                existentes += 1
    db.flush()
    relatorio.add("avaliacoes de desempenho", criados, existentes)


# --------------------------------------------------------------- 4. FORMACAO


CATALOGO_FORMACAO = [
    ("Prevencao e proteccao no trabalho", "Seguranca e saude no trabalho, riscos da funcao e uso de EPI."),
    ("Regulamentacao de seguros", "Requisitos do regime de seguros e obrigações do tomador do seguro."),
    ("Atencao ao cliente e comunicacao", "Escuta activa, tratamento de reclamações e promessa de valor."),
    ("Lideranca e feedback", "Conducao de reunioes, feedback estruturado e desenvolvimento da equipa."),
    ("Excel avancado", "Analise de dados, tabelas dinamicas e automacao de relatorios."),
    ("Fiscalidade e controlo interno", "Impostos, retencoes e segregacao de funcoes."),
    ("Ciberseguranca", "Proteccao de dados, boas praticas de senha e resposta a incidentes."),
    ("Gestao de conflitos", "Negociacao, mediação e des-escalonamento de conflitos."),
    ("Gesao documental e arquivo", "Organizacao, digitalizacao e conservacao de documentos."),
    ("Primeiros socorros", "Prestacao de primeiros socorros em contexto laboral."),
    ("Analise de dados e indicadores", "Construcao de indicadores de gestao e leitura de dashboards."),
    ("Conducao de reunioes e apresentacoes", "Preparacao, dinamizacao e conclusoes de reunioes."),
    ("Etica e compliance", "Codigo de etica, prevencao de conflitos de interesse e denuncia."),
]


def _semear_formacao(db, company, colaboradores, ciclos, relatorio):
    """
    Tres planos de formacao (ano anterior, ano corrente, proximo ano) e acoes
    distribuidas pelos colaboradores. As acoes com origem SISTEMA correspondem a
    quem teve nota baixa na avaliacao — a regra do manual (nota < 3,5).
    """
    ano = TODAY.year
    planos = [
        (f"Plano de Formacao {ano - 1}", TrainingPlanStatus.APROVADO),
        (f"Plano de Formacao {ano}", TrainingPlanStatus.EM_EXECUCAO),
        (f"Plano de Formacao {ano + 1}", TrainingPlanStatus.RASCUNHO),
    ]
    criados = 0
    existentes = 0
    for nome, estado in planos:
        plano = (
            db.query(TrainingPlan)
            .filter(TrainingPlan.company_id == company.id, TrainingPlan.name == nome)
            .first()
        )
        if plano is None:
            plano = TrainingPlan(company_id=company.id, name=nome, status=estado)
            db.add(plano)
            db.flush()
            criados += 1
        else:
            existentes += 1

    ciclo_atual = next((c for n, c in ciclos.items() if int(n.split()[-1]) == ano), None)

    def _nota_de(user):
        if ciclo_atual is None:
            return None
        avaliacao = (
            db.query(Evaluation)
            .filter(
                Evaluation.cycle_id == ciclo_atual.id,
                Evaluation.collaborator_id == user.id,
            )
            .first()
        )
        return avaliacao.final_score if avaliacao else None

    for indice, user in enumerate(colaboradores):
        nota = _nota_de(user)
        # Duas acoes por colaborador, mais uma extra para quem tem nota baixa.
        escolha = [CATALOGO_FORMACAO[indice % len(CATALOGO_FORMACAO)]]
        escolha.append(CATALOGO_FORMACAO[(indice + 5) % len(CATALOGO_FORMACAO)])
        if nota is not None and nota < 3.5:
            escolha.append(("Apoio reforcado ao desempenho", "Acompanhamento individualizado com a chefia directa."))
        for posicao, (titulo, descricao) in enumerate(escolha):
            origem = TrainingSource.SISTEMA if titulo.startswith(("Apoio reforcado", "Excel avancado", "Analise de dados")) else TrainingSource.AREA
            if nota is not None and nota < 3.5 and posicao == 0:
                origem = TrainingSource.SISTEMA
            for nome_plano, _estado in planos[:2]:
                plano = (
                    db.query(TrainingPlan)
                    .filter(TrainingPlan.company_id == company.id, TrainingPlan.name == nome_plano)
                    .first()
                )
                if plano is None:
                    continue
                # No plano do ano anterior tudo esta concluido; no corrente, misturado.
                concluida = nome_plano.endswith(str(ano - 1))
                estado_acao = (
                    TrainingActionStatus.CONCLUIDA
                    if concluida
                    else (
                        TrainingActionStatus.APROVADA
                        if (indice + posicao) % 3
                        else TrainingActionStatus.PROPOSTA
                    )
                )
                acao = (
                    db.query(TrainingAction)
                    .filter(
                        TrainingAction.plan_id == plano.id,
                        TrainingAction.collaborator_id == user.id,
                        TrainingAction.title == titulo,
                    )
                    .first()
                )
                if acao is None:
                    db.add(TrainingAction(
                        company_id=company.id,
                        plan_id=plano.id,
                        collaborator_id=user.id,
                        title=titulo,
                        description=descricao,
                        source=origem,
                        status=estado_acao,
                    ))
                    criados += 1
                else:
                    existentes += 1
    db.flush()
    relatorio.add("plano e accoes de formacao", criados, existentes)


# --------------------------------------------------------- 5. DESENVOLVIMENTO


def _semear_desenvolvimento(db, company, colaboradores, capitao_humano, relatorio):
    """Planos Individuais de Desenvolvimento (PID) do ano anterior e do corrente."""
    ano = TODAY.year
    acoes_por_nivel = [
        [("Mentoria com a chefia directa", "Sessoes quinzenais de acompanhamento.", DevelopmentActionStatus.PENDENTE),
         ("Especializacao tecnica na area", None, DevelopmentActionStatus.CONCLUIDA),
         ("Formacao em lideranca", "Coaching e gestao de equipas.", DevelopmentActionStatus.PENDENTE)],
        [("Workshop de comunicacao", None, DevelopmentActionStatus.CONCLUIDA),
         ("Projeto transversal com outra direccao", "Grupo de trabalho sobre processos.", DevelopmentActionStatus.PENDENTE)],
    ]
    criados = 0
    existentes = 0
    for indice, user in enumerate(colaboradores):
        for ano_pid, estado_plan in ((ano - 1, DevelopmentPlanStatus.CONCLUIDO), (ano, DevelopmentPlanStatus.ABERTO)):
            plano = (
                db.query(DevelopmentPlan)
                .filter(
                    DevelopmentPlan.company_id == company.id,
                    DevelopmentPlan.collaborator_id == user.id,
                    DevelopmentPlan.year == ano_pid,
                )
                .first()
            )
            if plano is None:
                plano = DevelopmentPlan(
                    company_id=company.id,
                    collaborator_id=user.id,
                    year=ano_pid,
                    status=estado_plan,
                    created_by=capitao_humano.id if capitao_humano else user.id,
                )
                db.add(plano)
                db.flush()
                criados += 1
                for titulo, descricao, estado_acao in acoes_por_nivel[indice % len(acoes_por_nivel)]:
                    db.add(DevelopmentAction(
                        company_id=company.id,
                        plan_id=plano.id,
                        title=titulo,
                        description=descricao,
                        status=(
                            DevelopmentActionStatus.CONCLUIDA
                            if estado_plan == DevelopmentPlanStatus.CONCLUIDO
                            else estado_acao
                        ),
                    ))
                    criados += 1
            else:
                existentes += 1
    db.flush()
    relatorio.add("planos de desenvolvimento (PID)", criados, existentes)


# ------------------------------------------------------------- 6. DISCIPLINA

# Cada linha descreve um processo ate ao fim: a fase em que fica, os factos
# imputados, a nota de culpa, a defesa, a decisao e o desfecho. Os textos sao
# os que a aplicacao escreve em cada fase, para o dossier e o PDF ficarem
# coerentes com o estado do processo.
PROCESSOS_DISCIPLINARES = [
    {
        "fase": DisciplinaryPhase.INSTAURACAO,
        "dias": 6,
        "factos": (
            "No dia 12 do mes corrente, o arguido abandonou o posto de trabalho sem "
            "autorizacao durante o turno da manha, nao procedeu ao registo de presenca e "
            "nao apresentou qualquer justificacao. No dia seguinte, regressou sem "
            "prestar esclarecimentos sobre a ausencia."
        ),
        "antecedentes": "Ja foi instaurado um processo similar em 2024, arquivado sem medida.",
        "suspensao": False,
        "nota_culpa": None,
        "defesa": None,
        "decisao": None,
        "desfecho": DisciplinaryOutcome.PENDENTE,
    },
    {
        "fase": DisciplinaryPhase.NOTA_CULPA,
        "dias": 21,
        "factos": (
            "Entre os dias 3 e 7 do mes corrente, o arguido nao registou presenca no "
            "sistema e nao compareceu a duas reunioes de equipa. No dia 6, devolveu um "
            "equipamento de trabalho danificado, sem qualquer aviso previo."
        ),
        "antecedentes": "Sem antecedentes disciplinares.",
        "suspensao": False,
        "nota_culpa": (
            "Factos: o arguido nao compareceu as reunioes de equipa, ainda que tenha "
            "sido registada a sua presenca, e devolveu equipamento de trabalho "
            "danificado. Qualificacao: faltas injustificadas e mau uso de recursos da "
            "empresa, em desconformidade com o artigo 24 do Regulamento Interno."
        ),
        "defesa": None,
        "decisao": None,
        "desfecho": DisciplinaryOutcome.PENDENTE,
    },
    {
        "fase": DisciplinaryPhase.DEFESA,
        "dias": 32,
        "factos": (
            "O arguido faltou injustificadamente a quatro dias de trabalho consecutivos, "
            "nao apresentou atestado medico e deixou de responder as chamadas da chefia "
            "directa durante o periodo."
        ),
        "antecedentes": "Duas advertencias escritas em 2025 pela falta de pontualidade.",
        "suspensao": True,
        "nota_culpa": (
            "Factos: ausencia de quatro dias uteis consecutivos sem justificacao. "
            "Qualificacao: falta injustificada, em violacao do artigo 24 do "
            "Regulamento Interno, que exige a comunicacao previa de qualquer ausencia."
        ),
        "defesa": None,
        "decisao": None,
        "desfecho": DisciplinaryOutcome.PENDENTE,
    },
    {
        "fase": DisciplinaryPhase.DECISAO,
        "dias": 48,
        "factos": (
            "O arguido movimentou 4.500.000 Kz de um cliente para uma conta sua, sem "
            "autorizacao do titular da conta e sem registo no sistema, a 14 de Marco."
        ),
        "antecedentes": "Sem antecedentes.",
        "suspensao": False,
        "nota_culpa": (
            "Factos: movimentacao de fundos de cliente para conta particular, sem "
            "autorizacao e sem lancamento no sistema. Qualificacao: violacao do dever "
            "de sigilo e do principio da segregacao de funcoes previsto no artigo 12 do "
            "Codigo de Etica."
        ),
        "defesa": (
            "O arguido nega a movimentacao e afirma que a operacao foi feita por um "
            "colega, com quem partilha o terminal. Alega que a autorizacao verbal do "
            "gestor de conta existia. Reiteramos que nao houve qualquer documento."
        ),
        "decisao": None,
        "desfecho": DisciplinaryOutcome.PENDENTE,
    },
    {
        "fase": DisciplinaryPhase.CONHECIMENTO_DECISAO,
        "dias": 61,
        "factos": (
            "O arguido partiu sem aviso com pendencias de tres clientes, nao entregou o "
            "inventario nem a palavra-passe do sistema e nao compareceu a duas reunioes "
            "de passagem de turno."
        ),
        "antecedentes": "Sem antecedentes.",
        "suspensao": False,
        "nota_culpa": (
            "Factos: desempenho de funcao com pendencias, entrega incompleta do "
            "inventario e falta de comparencia as reunioes obrigatorias. Qualificacao: "
            "abandono de posto com responsabilidade sobre clientes."
        ),
        "defesa": (
            "O arguido sustenta que lhe foi pedido pelo superior hierarquico que "
            "deixasse a unidade antes do termo do aviso, e que a passagem de turno foi "
            "feita verbalmente com um colega."
        ),
        "decisao": (
            "A comissao, ouvido o arguido e analisadas as provas, decide aplicar a "
            "medida disciplinar de suspensao por 15 dias uteis, com melhoria do "
            "desempenho e plano de readmissao ao posto findo o periodo. A medida e' "
            "proporcional aos factos e nao afasta a responsabilidade civil eventual por "
            "perdas apuradas."
        ),
        "desfecho": DisciplinaryOutcome.SUSPENSAO,
    },
    {
        "fase": DisciplinaryPhase.ARQUIVADO,
        "dias": 96,
        "factos": (
            "O arguido partilhou os dados de dois clientes no sistema partilhado, sem "
            "autorizacao e sem base legal, comprometendo a privacidade dos titulares."
        ),
        "antecedentes": "Sem antecedentes disciplinares.",
        "suspensao": False,
        "nota_culpa": (
            "Factos: tratamento de dados de clientes fora do perfil atribuido e "
            "partilha de informacao com um terceiro nao autorizado. Qualificacao: "
            "violacao da politica de proteccao de dados e do dever de confidencialidade."
        ),
        "defesa": (
            "O arguido assume os factos e invoca a urgencia do atendimento ao cliente, "
            "tendo agido de boa fe para evitar a perda da operacao. Pede que a sancao "
            "seja apenas uma advertencia."
        ),
        "decisao": (
            "A comissao reconhece a gravidade da infracao e a existencia de dano "
            "efectivo aos titulares, mas pondera a ausencia de reiteracao e o uso de "
            "boa fe. Decide aplicar a medida disciplinar de repreensao, com advertencia "
            "de que a reincidencia acarreta sancao mais grave."
        ),
        "desfecho": DisciplinaryOutcome.REPREENSAO,
    },
    {
        "fase": DisciplinaryPhase.ARQUIVADO,
        "dias": 128,
        "factos": (
            "O arguido deixou de comparecer ao trabalho durante tres dias por motivo de "
            "evento familiar grave, sem entregar qualquer comprovativo no prazo "
            "estabelecido para o efeito."
        ),
        "antecedentes": "Um processo arquivado sem medida em 2023.",
        "suspensao": True,
        "nota_culpa": (
            "Factos: tres dias de ausencia nao comunicados, sem comprovativo no prazo. "
            "Qualificacao: falta injustificada, sem se verificar a possibilidade "
            "de justificacao posterior."
        ),
        "defesa": (
            "O arguido apresentou atestado medico familiar e provou que comunicou um "
            "colega no primeiro dia, que nao foi possivel entregar o documento no "
            "prazo. Pede o arquivamento do processo."
        ),
        "decisao": (
            "Analisada a defesa e o atestado apresentado, a comissao conclui que o "
            "arguido nao tinha comunicacao valida nem comprovacao dentro do prazo, "
            "mas que a circunstancia familiar e a prova apresentada justificam o "
            "arquivamento sem medida disciplinar. Determina-se o registo da situacao "
            "para acompanhamento."
        ),
        "desfecho": DisciplinaryOutcome.ARQUIVAMENTO,
    },
]


def _semear_disciplina(db, company, colaboradores, directores, capitao_humano, relatorio):
    """
    Semeia processos disciplinares em todas as fases, cada um com a comissao de
    tres directores e com os actos de cada fase preenchidos ate ao estado actual.
    """
    instrutor = capitao_humano or directores[0]
    papeis = [CommitteeRole.RELATOR, CommitteeRole.INSTRUTOR, CommitteeRole.PRESIDENTE]
    criados = 0
    existentes = 0
    ano = TODAY.year
    for indice, modelo in enumerate(PROCESSOS_DISCIPLINARES):
        arguido = colaboradores[(indice * 3 + 1) % len(colaboradores)]
        comissao = [directores[(indice + k) % len(directores)] for k in range(3)]
        comissao = list(dict.fromkeys(comissao))
        restantes = [d for d in directores if d not in comissao]
        while len(comissao) < 3 and restantes:
            comissao.append(restantes.pop(0))
        comissao = comissao[:3]

        referencia = f"{PREFIXO}-{ano}-{indice + 1:03d}"
        processo = (
            db.query(DisciplinaryProcess)
            .filter(
                DisciplinaryProcess.company_id == company.id,
                DisciplinaryProcess.reference == referencia,
            )
            .first()
        )
        if processo is not None:
            existentes += 1
            continue

        fase = modelo["fase"]
        instaurado = NOW - timedelta(days=modelo["dias"])
        processo = DisciplinaryProcess(
            company_id=company.id,
            accused_id=arguido.id,
            instructor_id=instrutor.id,
            reference=referencia,
            phase=fase,
            imputed_facts=modelo["factos"],
            disciplinary_record=modelo["antecedentes"],
            preventive_suspension=modelo["suspensao"],
            charge_note=modelo["nota_culpa"],
            charge_ack_at=None,
            defense_text=modelo["defesa"],
            defense_deadline=None,
            defense_submitted_at=None,
            decision_text=modelo["decisao"],
            outcome=modelo["desfecho"],
            decision_ack_at=None,
            created_at=instaurado,
            updated_at=instaurado,
        )

        # Preenche os actos anteriores a fase actual, com datas coerentes.
        if fase in (DisciplinaryPhase.DEFESA, DisciplinaryPhase.DECISAO,
                    DisciplinaryPhase.CONHECIMENTO_DECISAO, DisciplinaryPhase.ARQUIVADO):
            processo.charge_ack_at = instaurado + timedelta(days=4)
        if fase in (DisciplinaryPhase.DECISAO, DisciplinaryPhase.CONHECIMENTO_DECISAO,
                    DisciplinaryPhase.ARQUIVADO):
            prazo = instaurado + timedelta(days=14)
            processo.defense_deadline = prazo.date()
            processo.defense_submitted_at = prazo - timedelta(days=RNG.randint(1, 6))
        if fase == DisciplinaryPhase.DEFESA:
            # Processo aberto: o arguido tem 10 dias uteis para apresentar defesa.
            processo.defense_deadline = TODAY + timedelta(days=8)
        if fase in (DisciplinaryPhase.CONHECIMENTO_DECISAO, DisciplinaryPhase.ARQUIVADO):
            processo.decision_ack_at = instaurado + timedelta(days=25)
        db.add(processo)
        db.flush()
        criados += 1

        for posicao, membro in enumerate(comissao):
            db.add(DisciplinaryCommitteeMember(
                process_id=processo.id,
                user_id=membro.id,
                role=papeis[posicao],
            ))

        # Notificacoes e trilha de auditoria, como a aplicacao faz em cada fase.
        _notificar(db, company, arguido, "Processo disciplinar instaurado",
                   f"Foi instaurado o processo {referencia}. Pode consultar o processo e os factos.",
                   "disciplina", "/disciplina", dias=modelo["dias"])
        if modelo["nota_culpa"]:
            _notificar(db, company, arguido, "Nota de culpa",
                       f"Recebeu a nota de culpa do processo {referencia}. Tem 10 dias uteis para apresentar defesa.",
                       "disciplina", "/disciplina", dias=modelo["dias"] - 4)
        if modelo["decisao"]:
            _notificar(db, company, arguido, "Decisao disciplinar",
                       f"Foi emitida a decisao do processo {referencia}. Deve ler e assinar o conhecimento.",
                       "disciplina", "/disciplina", dias=modelo["dias"] - 25)
        for membro in comissao:
            _notificar(db, company, membro, "Comissao disciplinar designada",
                       f"Foi nomeado membro da comissao disciplinar do processo {referencia}.",
                       "disciplina", "/disciplina", dias=modelo["dias"])
        _auditar(db, company, instrutor, "disciplina.instaurada",
                 f"Processo {referencia} instaurado contra {arguido.full_name}.", dias=modelo["dias"])
        if modelo["decisao"]:
            _auditar(db, company, instrutor, "disciplina.decisao",
                     f"Decisao emitida no processo {referencia}: {modelo['desfecho'].value}.",
                     dias=modelo["dias"] - 25)
        if fase == DisciplinaryPhase.ARQUIVADO:
            _auditar(db, company, instrutor, "disciplina.arquivado",
                     f"Processo {referencia} arquivado com desfecho {modelo['desfecho'].value}.",
                     dias=modelo["dias"] - 30)
    db.flush()
    relatorio.add("processos disciplinares", criados, existentes)


# -------------------------------------------------------------- 7. AUSENCIAS


def _semear_ausencias(db, company, colaboradores, relatorio):
    """Ausencias variadas: ferias, faltas justificadas, doenca e maternidade."""
    criados = 0
    existentes = 0
    modelos = [
        (LeaveType.FERIAS, -340, 15, LeaveStatus.APROVADA, True, "Ferias anuais do ano anterior"),
        (LeaveType.FERIAS, -300, 10, LeaveStatus.APROVADA, True, "Ferias anuais"),
        (LeaveType.FERIAS, -150, 12, LeaveStatus.APROVADA, True, "Ferias anuais"),
        (LeaveType.FERIAS, 21, 14, LeaveStatus.PENDENTE_DIR, False, "Pedido de ferias para o proximo trimestre"),
        (LeaveType.FERIAS, 46, 8, LeaveStatus.PENDENTE_DIR, False, "Pedido de ferias para a proxima segunda-feira"),
        (LeaveType.FALTA, -95, 1, LeaveStatus.JUSTIFICADA, False, "Atestado medico apresentado"),
        (LeaveType.FALTA, -60, 1, LeaveStatus.JUSTIFICADA, False, "Justificacao de falta por motivo familiar"),
        (LeaveType.FALTA, -30, 1, LeaveStatus.RECUSADA, False, "Falta sem justificacao"),
        (LeaveType.FALTA, -18, 2, LeaveStatus.JUSTIFICADA, False, "Atestado medico de dois dias"),
        (LeaveType.DOENCA, -200, 20, LeaveStatus.APROVADA, True, "Afastamento por doenca prolongada"),
        (LeaveType.DOENCA, -400, 12, LeaveStatus.APROVADA, True, "Afastamento por doenca"),
        (LeaveType.MATERNIDADE, -320, 120, LeaveStatus.APROVADA, True, "Licenca de maternidade"),
        (LeaveType.MATERNIDADE, -600, 120, LeaveStatus.APROVADA, True, "Licenca de maternidade"),
    ]
    for indice, user in enumerate(colaboradores):
        for deslocamento, (tipo, dias_rel, dias, estado, averbado, motivo) in enumerate(modelos):
            # Cada colaborador recebe um subconjunto diferente dos modelos.
            if (indice + deslocamento) % 3 == 2:
                continue
            inicio = TODAY + timedelta(days=dias_rel)
            existente = (
                db.query(LeaveRequest)
                .filter(
                    LeaveRequest.company_id == company.id,
                    LeaveRequest.collaborator_id == user.id,
                    LeaveRequest.leave_type == tipo,
                    LeaveRequest.start_date == inicio,
                )
                .first()
            )
            if existente is not None:
                existentes += 1
                continue
            db.add(LeaveRequest(
                company_id=company.id,
                collaborator_id=user.id,
                leave_type=tipo,
                start_date=inicio,
                end_date=inicio + timedelta(days=dias - 1),
                days=dias,
                reason=motivo,
                document_name="Atestado medico.pdf" if tipo == LeaveType.FALTA else None,
                status=estado,
                rejection_reason=(
                    "Periodo com sobreposicao de equipa e indisponibilidade de cobertura."
                    if estado == LeaveStatus.RECUSADA
                    else None
                ),
                averbado=averbado,
            ))
            criados += 1

    db.flush()
    relatorio.add("ferias e ausencias", criados, existentes)

# ------------------------------------------------- 8. PERCURSO E REMUNERACAO


def _semear_percurso(db, company, colaboradores, relatorio):
    """Louvores, promocoes e nomeacoes, mais a progressao salarial por ano."""
    ano = TODAY.year
    criados = 0
    existentes = 0
    eventos = [
        (CareerEventType.LOUVOR, -180, "Reconhecimento pelo desempenho no trimestre",
         "Mencao de elogio pela recuperacao de um processo de reinstalacao complexo."),
        (CareerEventType.PROMOCAO, -400, "Promocao a especialista da area",
         "Promocao com atribuicao de responsabilidade tecnica sobre a carteira."),
        (CareerEventType.NOMEACAO, -90, "Nomeacao para o grupo de trabalho de qualidade",
         "Participa no grupo transversal que revisa os processos da empresa."),
        (CareerEventType.LOUVOR, -45, "Apoio a colega para alem do turno",
         "Apoio a colega numa situacao de urgencia durante o turno da noite."),
        (CareerEventType.NOMEACAO, -240, "Nomeacao para a comissao de recebimentos",
         "Participa na comissao que definiu as novas regras de recebimento."),
    ]
    for indice, user in enumerate(colaboradores):
        for deslocamento, (tipo, dias_rel, titulo, descricao) in enumerate(eventos):
            if (indice + deslocamento) % 4 == 3:
                continue
            titulo_unico = f"{PREFIXO} — {titulo}"
            existente = (
                db.query(CareerEvent)
                .filter(
                    CareerEvent.company_id == company.id,
                    CareerEvent.collaborator_id == user.id,
                    CareerEvent.title == titulo_unico,
                )
                .first()
            )
            if existente is not None:
                existentes += 1
                continue
            db.add(CareerEvent(
                company_id=company.id,
                collaborator_id=user.id,
                event_type=tipo,
                event_date=TODAY + timedelta(days=dias_rel),
                title=titulo_unico,
                description=descricao,
            ))
            criados += 1

        for ano_registo in (ano - 2, ano - 1, ano):
            registo = (
                db.query(SalaryRecord)
                .filter(
                    SalaryRecord.company_id == company.id,
                    SalaryRecord.collaborator_id == user.id,
                    SalaryRecord.year == ano_registo,
                )
                .first()
            )
            if registo is not None:
                existentes += 1
                continue
            # Salario base com progressao anual de cerca de 8%.
            base = 240000 + indice * 14000
            multiplicador = {ano - 2: 0.88, ano - 1: 0.95, ano: 1.0}[ano_registo]
            db.add(SalaryRecord(
                company_id=company.id,
                collaborator_id=user.id,
                year=ano_registo,
                gross_salary=round(base * multiplicador, -2),
                salary_grade=("Tecnico I", "Tecnico II", "Tecnico III", "Analista I")[indice % 4],
            ))
            criados += 1

        for periodo in (f"{ano - 2}", f"{ano - 1}"):
            registo = (
                db.query(AttendanceRecord)
                .filter(
                    AttendanceRecord.company_id == company.id,
                    AttendanceRecord.collaborator_id == user.id,
                    AttendanceRecord.period == periodo,
                )
                .first()
            )
            if registo is not None:
                existentes += 1
                continue
            db.add(AttendanceRecord(
                company_id=company.id,
                collaborator_id=user.id,
                period=periodo,
                present_days=232 + (indice % 7),
                justified_absences=2 + (indice % 5),
                unjustified_absences=indice % 3,
                vacation_days_taken=20 + (indice % 9),
            ))
            criados += 1
    db.flush()
    relatorio.add("percurso e remuneracao", criados, existentes)


# --------------------------------------------------------------- 9. TALENTO


def _semear_talento(db, company, colaboradores, directores, ciclos, capitao_humano, relatorio):
    """Matriz 9-Box do ciclo corrente e plano de sucessao com titular e sucessor."""
    criados = 0
    existentes = 0
    ano = TODAY.year
    autor = capitao_humano.id if capitao_humano else colaboradores[0].id
    for indice, user in enumerate(colaboradores):
        desempenho = 3.4 + ((indice * 3) % 17) / 10.0
        potencial = [PotentialLevel.ALTO, PotentialLevel.MEDIO, PotentialLevel.MEDIO, PotentialLevel.BAIXO][indice % 4]
        for nome_ciclo, ciclo in sorted(ciclos.items()):
            if int(nome_ciclo.split()[-1]) != ano:
                continue
            existente = (
                db.query(TalentMatrix)
                .filter(
                    TalentMatrix.cycle_id == ciclo.id,
                    TalentMatrix.collaborator_id == user.id,
                )
                .first()
            )
            if existente is not None:
                existentes += 1
                continue
            if potencial == PotentialLevel.ALTO:
                posicao = "Investidor de alto potencial"
                nota = "pronto para maior responsabilidade"
            elif potencial == PotentialLevel.BAIXO:
                posicao = "Desempenho a consolidar"
                nota = "acompanhamento reforcado e plano de formacao"
            else:
                posicao = "Desempenho solido e consistente"
                nota = "manter o plano de desenvolvimento actual"
            db.add(TalentMatrix(
                company_id=company.id,
                cycle_id=ciclo.id,
                collaborator_id=user.id,
                potential=potencial,
                position=posicao,
                risk_of_exit=indice % 9 == 0,
                notes=f"Desempenho registado no ciclo: {desempenho:.1f}. Avaliacao do comite: {nota}.",
                created_by=autor,
            ))
            criados += 1

    # Plano de sucessao: cada cargo-chave tem titular e sucessor.
    sucessoes = [
        ("Director Comercial", 0, 0, ReadinessLevel.PRONTO_AGORA),
        ("Director Financeiro", 3, 1, ReadinessLevel.EM_6_MESES),
        ("Director de Sistemas", 2, 2, ReadinessLevel.EM_12_MESES),
        ("Chefe de Sinistros", 1, 3, ReadinessLevel.EM_12_MESES),
        ("Responsavel de Conformidade", None, 4, ReadinessLevel.NAO_QUALIFICADO),
    ]
    for cargo, indice_titular, indice_sucessor, prontidao in sucessoes:
        sucessor = colaboradores[indice_sucessor % len(colaboradores)]
        titular = directores[indice_titular % len(directores)] if indice_titular is not None else None
        existente = (
            db.query(SuccessionPlan)
            .filter(
                SuccessionPlan.company_id == company.id,
                SuccessionPlan.role_title == f"{PREFIXO} — {cargo}",
            )
            .first()
        )
        if existente is not None:
            existentes += 1
            continue
        db.add(SuccessionPlan(
            company_id=company.id,
            role_title=f"{PREFIXO} — {cargo}",
            incumbent_id=titular.id if titular else None,
            successor_id=sucessor.id,
            readiness=prontidao,
            risk_of_exit=indice_titular in (0, 3),
            notes=f"Sucessor identificado: {sucessor.full_name}. Prontidao avaliada pelo comite de talento.",
            created_by=autor,
        ))
        criados += 1
    db.flush()
    relatorio.add("matriz de talento e sucessao", criados, existentes)


# -------------------------------------------------------------- 10. CULTURA


DIMENSOES_PULSO = [
    "confianca_lideranca",
    "clareza_estrategica",
    "reconhecimento",
    "equilibrio_vida",
    "carga_trabalho",
    "recomendaria_empresa",
]


def _semear_cultura(db, company, colaboradores, relatorio):
    """
    Tres inqueritos-pulso (um fechado, outro fechado e o corrente aberto) com
    respostas anonimas suficientes para a regra dos 5 e participacoes registadas.
    """
    ano = TODAY.year
    criados = 0
    existentes = 0
    pulsos = [
        (f"{PREFIXO} — Pulso de cultura {ano - 1} (4.º trimestre)", -80, SurveyStatus.FECHADO, 0.62),
        (f"{PREFIXO} — Pulso de cultura {ano} (1.º trimestre)", -170, SurveyStatus.FECHADO, 0.70),
        (f"{PREFIXO} — Pulso de cultura {ano} (2.º trimestre)", -12, SurveyStatus.ABERTO, 0.0),
    ]
    for titulo, dias_rel, estado, tendencia in pulsos:
        pulso = (
            db.query(Survey)
            .filter(Survey.company_id == company.id, Survey.title == titulo)
            .first()
        )
        if pulso is None:
            pulso = Survey(
                company_id=company.id,
                title=titulo,
                dimensions=json.dumps(DIMENSOES_PULSO),
                status=estado,
                created_at=NOW - timedelta(days=dias_rel),
            )
            db.add(pulso)
            db.flush()
            criados += 1
        else:
            existentes += 1

        # Respostas anonimas: o valor de cada dimensao deriva da tendencia do
        # pulso, para que o grafico mostre uma evolucao coerente.
        total = 14 if estado == SurveyStatus.ABERTO else 18
        if db.query(SurveyResponse).filter(
            SurveyResponse.survey_id == pulso.id
        ).count() == 0:
            base = 3.4 + tendencia * 1.2
            for indice in range(total):
                respostas = {}
                for posicao, dimensao in enumerate(DIMENSOES_PULSO):
                    if dimensao == "recomendaria_empresa":
                        respostas[dimensao] = max(1, min(5, round(base + RNG.uniform(-1, 1))))
                    else:
                        respostas[dimensao] = max(
                            1, min(5, round(base + RNG.uniform(-0.9, 0.9) - posicao * 0.05))
                        )
                db.add(SurveyResponse(
                    company_id=company.id,
                    survey_id=pulso.id,
                    answers=json.dumps(respostas, ensure_ascii=False),
                    submitted_at=NOW - timedelta(days=dias_rel + RNG.randint(0, 6)),
                ))
                criados += 1

        # Participacao: quantos responderam (sem conteudo associado).
        if estado != SurveyStatus.ABERTO:
            for indice, user in enumerate(colaboradores):
                if indice >= total:
                    break
                participacao = (
                    db.query(SurveyParticipation)
                    .filter(
                        SurveyParticipation.survey_id == pulso.id,
                        SurveyParticipation.user_id == user.id,
                    )
                    .first()
                )
                if participacao is None:
                    db.add(SurveyParticipation(
                        company_id=company.id,
                        survey_id=pulso.id,
                        user_id=user.id,
                        participated_at=NOW - timedelta(days=dias_rel + RNG.randint(0, 6)),
                    ))
                    criados += 1
                else:
                    existentes += 1

    relatorio_pulso = (
        db.query(CultureReport)
        .filter(CultureReport.company_id == company.id)
        .first()
    )
    if relatorio_pulso is None:
        relatorio_pulso = CultureReport(company_id=company.id)
        db.add(relatorio_pulso)
        criados += 1
    else:
        existentes += 1
    relatorio_pulso.enps = relatorio_pulso.enps or "+47"
    relatorio_pulso.participation = relatorio_pulso.participation or "78%"
    relatorio_pulso.pulses_note = relatorio_pulso.pulses_note or (
        "Tres pulsos colhidos. Participacao acima do minimo de revelacao em todos."
    )
    relatorio_pulso.dimensions_json = relatorio_pulso.dimensions_json or json.dumps([
        {"name": "Confianca na lideranca", f"y{ano - 2}": 58, f"y{ano - 1}": 66, f"y{ano}": 74},
        {"name": "Clareza estrategica", f"y{ano - 2}": 61, f"y{ano - 1}": 65, f"y{ano}": 71},
        {"name": "Reconhecimento", f"y{ano - 2}": 54, f"y{ano - 1}": 63, f"y{ano}": 70},
        {"name": "Equilibrio vida-trabalho", f"y{ano - 2}": 66, f"y{ano - 1}": 64, f"y{ano}": 68},
        {"name": "Seguranca e saude no trabalho", f"y{ano - 2}": 72, f"y{ano - 1}": 78, f"y{ano}": 81},
    ], ensure_ascii=False)
    relatorio_pulso.recommendations_json = relatorio_pulso.recommendations_json or json.dumps([
        "Reforcar a comunicacao das prioridades trimestrais em todas as direccoes.",
        "Aumentar o reconhecimento publico das equipas com melhor desempenho.",
        "Manter o programa de mentoria para preparar sucessores.",
        "Rever a carga de trabalho no pico de sinistros do ultimo trimestre.",
    ], ensure_ascii=False)
    db.flush()
    relatorio.add("cultura (pulsos e relatorio)", criados, existentes)

# ------------------------------------------- 11. NOTIFICACOES, CHAT, AUDITORIA


def _semear_comunicacao(db, company, colaboradores, directores, capitao_humano, comissao, administracao, ciclos, relatorio):
    """Notificacoes, conversas e trilha de auditoria com eventos de todo o periodo."""
    criados = 0
    existentes = 0
    ano = TODAY.year
    comissao = comissao or capitao_humano or directores[0]
    administracao = administracao or comissao

    for indice, user in enumerate(colaboradores):
        _notificar(db, company, user, f"Ciclo de avaliacao {ano} disponivel",
                   "O ciclo anual de avaliacao esta disponivel. Preencha a sua autoavaliacao ate ao fim do mes.",
                   "avaliacao", "/avaliacoes", dias=30)
        _notificar(db, company, user, "Plano de formacao actualizado",
                   "O plano de formacao do ano foi actualizado com novas acoes aprovadas.",
                   "formacao", "/formacao", dias=18, is_read=indice % 3 == 0)
        if indice % 2 == 0:
            _notificar(db, company, user, "Pedido de ferias em analise",
                       "O seu pedido de ferias foi recebido e esta a aguardar aprovacao da chefia.",
                       "ausencia", "/ausencias", dias=9)
        if indice % 4 == 1:
            _notificar(db, company, user, "Regulamento Interno actualizado",
                       "O Regulamento Interno foi actualizado. Confirme a leitura no dossier.",
                       "dossie", "/portal", dias=52, is_read=True)

    _notificar(db, company, capitao_humano, "Ciclo de avaliacao em curso",
               f"O ciclo {ano} tem avaliacoes em varias fases. Consulta o painel de progresso.",
               "avaliacao", "/avaliacoes", dias=5)
    _notificar(db, company, comissao, "Recursos de avaliacao para decisao",
               "Ha avaliacoes em fase de comissao à espera de decisao.",
               "avaliacao", "/avaliacoes", dias=7)
    _notificar(db, company, administracao, "Ciclo pronto para validacao",
               "Ha avaliacoes fechadas à espera de validacao pela Administracao.",
               "avaliacao", "/avaliacoes", dias=11)
    for indice, director in enumerate(directores):
        _notificar(db, company, director, "Avaliacoes da sua equipa por avaliar",
                   "Tens avaliacoes da tua equipa na fase de avaliacao de director.",
                   "avaliacao", "/avaliacoes", dias=3 + indice)

    # Conversas: o par (remetente, destinatario) e' a chave de idempotencia,
    # por isso procuramos pelo corpo exacto da mensagem.
    conversas = [
        (capitao_humano, directores[0], "Bom dia. O ciclo de avaliacao ja esta disponivel para as equipas.", 26),
        (directores[0], capitao_humano, "Bom dia. A equipa de Vendas ja comecou a organizar os objectivos.", 25),
        (directores[0], colaboradores[0], "A sua autoavaliacao esta pendente. Pode submeter quando estiver concluida.", 20),
        (colaboradores[0], directores[0], "Bom dia, ja submetei. Obrigado pelo retorno.", 19),
        (capitao_humano, colaboradores[3], "Recebemos o seu pedido de rectification de ficha. Vamos analisar.", 40),
        (colaboradores[3], capitao_humano, "Obrigado. Fico a aguardar.", 39),
        (capitao_humano, colaboradores[7], "A acao de formacao em Excel avancado foi aprovada para si.", 15),
        (colaboradores[7], capitao_humano, "Perfeito, obrigado. Vou tratar da inscricao esta semana.", 14),
        (directores[2], colaboradores[7], "Preciso de um breve alinhamento sobre os incidentes em aberto.", 8),
        (colaboradores[7], directores[2], "Combinado, passo no seu escritorio as 10h.", 7),
        (comissao, capitao_humano, "A comissao de avaliacao pediu para agendar a sessao de recursos.", 12),
        (capitao_humano, comissao, "Fica marcada para a proxima quarta-feira as 15h.", 11),
    ]

    for remetente, destinatario, corpo, dias_atras in conversas:
        if remetente is None or destinatario is None:
            continue
        existente = (
            db.query(ChatMessage)
            .filter(
                ChatMessage.company_id == company.id,
                ChatMessage.sender_id == remetente.id,
                ChatMessage.recipient_id == destinatario.id,
                ChatMessage.body == corpo,
            )
            .first()
        )
        if existente is not None:
            existentes += 1
            continue
        db.add(ChatMessage(
            company_id=company.id,
            sender_id=remetente.id,
            recipient_id=destinatario.id,
            body=corpo,
            is_read=dias_atras > 10,
            created_at=NOW - timedelta(days=dias_atras, minutes=RNG.randint(0, 300)),
        ))
        criados += 1

    # Trilha de auditoria: o que a Administracao audita.
    eventos = [
        ("ciclo.avaliacao_criado", f"Ciclo {ano} aberto com formulario de avaliacao configurado.", 40),
        ("avaliacao.autoavaliacao", "Autoavaliacoes submetidas pelas equipas.", 22),
        ("avaliacao.director", "Avaliacoes de director concluidas.", 14),
        ("avaliacao.recurso", "Recurso interposto e encaminhado para a comissao.", 7),
        ("formacao.plano_aprovado", f"Plano de formacao {ano} aprovado pela Administracao.", 60),
        ("formacao.acao_concluida", "Accoes de formacao concluidas e registadas.", 30),
        ("disciplina.instaurada", "Processo disciplinar instaurado apos participacao.", 5),
        ("ficha.rectificada", "Pedido de rectificacao de ficha deferido.", 40),
        ("dossie.assinatura", "Assinaturas de adesao registadas.", 90),
        ("cultura.pulso_fechado", "Inquerito-pulso fechado com participacao acima do minimo.", 80),
        ("talento.matriz", "Matriz de talento actualizada pelo comite.", 35),
        ("sucessao.plano", "Plano de sucessao actualizado com sucessores.", 35),
    ]
    for accao, detalhe, dias_atras in eventos:
        if _auditar(db, company, administracao, accao, detalhe, dias=dias_atras):
            criados += 1
        else:
            existentes += 1
    db.flush()
    relatorio.add("notificacoes, chat e auditoria", criados, existentes)


# --------------------------------------------------------- 12. DOSSIER E ORGAOS


DOCUMENTOS_ADICIONAIS = [
    ("Politica de Seguranca e Saude no Trabalho",
     "Regras de prevencao, uso de equipamento de proteccao e comunicacao de acidentes."),
    ("Politica de Proteccao de Dados",
     "Princípios de tratamento de dados pessoais e dever de confidencialidade."),
    ("Codigo de Conducta eiquette",
     "Normas de convivio profissional e de relacionamento com clientes."),
]



def _semear_dossie(db, company, colaboradores, directores, relatorio):
    """Documentos adicionais, registos de leitura e orgãos sociais completos."""
    criados = 0
    existentes = 0
    documentos = {}
    for titulo, conteudo in DOCUMENTOS_ADICIONAIS:
        documento = (
            db.query(Document)
            .filter(Document.company_id == company.id, Document.title == titulo)
            .first()
        )
        if documento is None:
            documento = Document(company_id=company.id, title=titulo, content=conteudo)
            db.add(documento)
            db.flush()
            criados += 1
        else:
            existentes += 1
        documentos[titulo] = documento

    # Cada colaborador leu pelo menos um dos documentos novos.
    for indice, user in enumerate(list(colaboradores) + list(directores)):
        documento = documentos[DOCUMENTOS_ADICIONAIS[indice % len(DOCUMENTOS_ADICIONAIS)][0]]
        leitura = (
            db.query(DocumentRead)
            .filter(
                DocumentRead.company_id == company.id,
                DocumentRead.document_id == documento.id,
                DocumentRead.user_id == user.id,
            )
            .first()
        )
        if leitura is None:
            db.add(DocumentRead(
                company_id=company.id,
                document_id=documento.id,
                user_id=user.id,
                read_at=NOW - timedelta(days=RNG.randint(10, 120)),
            ))
            criados += 1
        else:
            existentes += 1

    # Orgaos sociais: distribui os directores pelos quatro orgaos.
    from app.models.enums import CompanyOrgan

    cargos = {
        CompanyOrgan.CONSELHO_ADMINISTRACAO: ["Presidente do Conselho", "Vogal", "Vogal"],
        CompanyOrgan.COMISSAO_EXECUTIVA: ["Director Executivo", "Director Executivo Adjunto", "Membro"],
        CompanyOrgan.CONSELHO_FISCAL: ["Presidente do Conselho Fiscal", "Fiscal", "Fiscal"],
        CompanyOrgan.MESA_ASSEMBLEIA: ["Presidente da Assembleia", "Secretario", "Secretario"],
    }
    if directores:
        for indice, director in enumerate(directores):
            orgao = list(cargos)[indice % len(cargos)]
            existente = (
                db.query(OrganMember)
                .filter(
                    OrganMember.company_id == company.id,
                    OrganMember.organ == orgao,
                    OrganMember.user_id == director.id,
                )
                .first()
            )
            if existente is not None:
                existentes += 1
                continue
            db.add(OrganMember(
                company_id=company.id,
                organ=orgao,
                user_id=director.id,
                organ_role=cargos[orgao][indice % len(cargos[orgao])],
            ))
            criados += 1
    db.flush()
    relatorio.add("dossie e orgaos sociais", criados, existentes)


# --------------------------------------------------------------------- MAIN


def _resumo(db, company):
    """Confere a coerencia do que foi semeado e imprime o estado final."""
    linhas = [
        ("colaboradores", db.query(User).filter(
            User.company_id == company.id, User.role == UserRole.COLABORADOR).count()),
        ("avaliacoes", db.query(Evaluation).filter(Evaluation.company_id == company.id).count()),
        ("acoes de formacao", db.query(TrainingAction).filter(TrainingAction.company_id == company.id).count()),
        ("processos disciplinares", db.query(DisciplinaryProcess).filter(
            DisciplinaryProcess.company_id == company.id).count()),
        ("ausencias", db.query(LeaveRequest).filter(LeaveRequest.company_id == company.id).count()),
        ("acoes de desenvolvimento", db.query(DevelopmentAction).filter(
            DevelopmentAction.company_id == company.id).count()),
        ("eventos de percurso", db.query(CareerEvent).filter(CareerEvent.company_id == company.id).count()),
        ("registos salariais", db.query(SalaryRecord).filter(SalaryRecord.company_id == company.id).count()),
        ("respostas a pulsos", db.query(SurveyResponse).filter(SurveyResponse.company_id == company.id).count()),
        ("notificacoes", db.query(Notification).filter(Notification.company_id == company.id).count()),
        ("mensagens de chat", db.query(ChatMessage).filter(ChatMessage.company_id == company.id).count()),
        ("eventos de auditoria", db.query(AuditEvent).filter(AuditEvent.company_id == company.id).count()),
    ]
    print()
    print(f"Estado final em '{company.name}' (ID {company.id}):")
    for nome, total in linhas:
        print(f"  {nome:<28}{total}")


def semear(db, company):
    """
    Enriquece uma empresa com o conjunto completo de dados de demonstracao.
    Idempotente: pode correr em qualquer arranque sem duplicar registos.
    Devolve o `Relatorio` com o que foi criado e o que ja existia.
    """
    colaboradores, directores, capitao_humano, comissao, administracao = _contas(db, company)
    relatorio = Relatorio()
    _semear_fichas(db, company, colaboradores, relatorio)
    ciclos = _semear_ciclos(db, company, relatorio)
    _semear_avaliacoes(db, company, colaboradores, directores, ciclos, relatorio)
    _semear_formacao(db, company, colaboradores, ciclos, relatorio)
    _semear_desenvolvimento(db, company, colaboradores, capitao_humano, relatorio)
    _semear_disciplina(db, company, colaboradores, directores, capitao_humano, relatorio)
    _semear_ausencias(db, company, colaboradores, relatorio)
    _semear_percurso(db, company, colaboradores, relatorio)
    _semear_talento(db, company, colaboradores, directores, ciclos, capitao_humano, relatorio)
    _semear_cultura(db, company, colaboradores, relatorio)
    _semear_comunicacao(
        db, company, colaboradores, directores, capitao_humano, comissao, administracao, ciclos, relatorio
    )
    _semear_dossie(db, company, colaboradores, directores, relatorio)
    db.commit()
    return relatorio


def semear_por_nome(nome_ou_id, password=None, criar_se_nao_existir=False):
    """
    Liga a semente ao arranque da aplicacao: procura a empresa por nome ou ID,
    garante as contas de demo e semeia. Devolve o relatorio, ou None se o alvo
    estiver vazio. Com `criar_se_nao_existir` cria a empresa (util num ambiente
    novo); caso contrario apenas avisa.
    """
    if not nome_ou_id:
        return None
    Base.metadata.create_all(bind=engine)
    ensure_schema_columns()
    db = SessionLocal()
    try:
        alvo = nome_ou_id.strip()
        company = None
        if alvo.isdigit():
            company = db.get(Company, int(alvo))
        if company is None:
            company = (
                db.query(Company).filter(Company.name.ilike(f"%{alvo}%")).order_by(Company.id).first()
            )
        if company is None and criar_se_nao_existir:
            company = Company(name=alvo)
            db.add(company)
            db.flush()
            print(f"[semente] Empresa '{alvo}' criada.")
        if company is None:
            print(f"[semente] Empresa '{alvo}' nao encontrada: nada a semear.")
            db.rollback()
            return None
        if password:
            _garantir_contas(
                db, company, password, completar=criar_se_nao_existir
            )
        relatorio = semear(db, company)
        print(f"[semente] '{company.name}' (ID {company.id}): {relatorio.resumo()}")
        _resumo(db, company)
        return relatorio
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main():
    args = _parse_args()
    password = os.getenv("DEMO_PASSWORD") or os.getenv("DEEP_SEED_PASSWORD")
    if password and not 8 <= len(password) <= 72:
        raise SystemExit("DEMO_PASSWORD deve ter entre 8 e 72 caracteres.")
    if args.dry_run:
        Base.metadata.create_all(bind=engine)
        ensure_schema_columns()
        db = SessionLocal()
        try:
            company = _find_company(db, args.company_id, args.company_name)
            colaboradores, directores, _, _, _ = _contas(db, company)
            print(f"Empresa: {company.name} (ID {company.id})")
            print(f"Colaboradores: {len(colaboradores)} | Directores: {len(directores)}")
            print("Este script nao altera nada em --dry-run.")
        finally:
            db.close()
        return
    if not args.confirm_demo:
        raise SystemExit("Use --confirm-demo para autorizar a inserção dos dados.")
    Base.metadata.create_all(bind=engine)
    ensure_schema_columns()
    db = SessionLocal()
    try:
        company = _find_company(db, args.company_id, args.company_name)
        if password:
            _garantir_contas(db, company, password, completar=True)
        relatorio = semear(db, company)
        relatorio.imprimir()
        _resumo(db, company)
    except ValueError as erro:
        db.rollback()
        raise SystemExit(str(erro)) from erro
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
