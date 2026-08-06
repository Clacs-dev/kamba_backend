"""
Enumerações partilhadas pelos modelos do KAMBA.
"""
import enum


class UserRole(str, enum.Enum):
    """
    Os cinco perfis descritos no manual (secção 1.1).

    O acesso obedece ao princípio da necessidade de conhecer: cada perfil
    tem competências distintas na plataforma.
    """
    COLABORADOR = "colaborador"          # portal pessoal, autoavaliação, assinaturas
    DIRECTOR = "director"                # avalia a equipa, regista incidentes
    CAPITAL_HUMANO = "capital_humano"    # gere colaboradores, instrui processos
    COMISSAO_AVALIACAO = "comissao"      # decide recursos das avaliações
    ADMINISTRACAO = "administracao"      # valida avaliações, acede a relatórios

    # Perfil técnico, fora dos cinco do manual: o operador da CLACS que gere
    # várias empresas (o "selector de empresa" da secção 1.2). Opcional.
    SUPERADMIN = "superadmin"

class ContractType(str, enum.Enum):
    """Tipo de vínculo laboral (secção 2.1 do manual)."""
    EFETIVO = "efetivo"
    TERMO_CERTO = "termo_certo"
    TERMO_INCERTO = "termo_incerto"
    ESTAGIO = "estagio"
    PRESTACAO_SERVICOS = "prestacao_servicos"

class DocumentType(str, enum.Enum):
    """Tipos de documento do dossier individual (secção 2.4)."""
    CONTRATO = "contrato"
    REGULAMENTO_INTERNO = "regulamento_interno"
    CODIGO_ETICA = "codigo_etica"
    POLITICA_ASSIDUIDADE = "politica_assiduidade"
    POLITICA_REMUNERACAO = "politica_remuneracao"
    REGULAMENTO_AVALIACAO = "regulamento_avaliacao"
    OUTRO = "outro"


class SignatureType(str, enum.Enum):
    """As três assinaturas digitais de adesão (secção 2.2)."""
    REGULAMENTO_POLITICAS = "regulamento_politicas"
    TERMOS_PORTAL = "termos_portal"
    CONSENTIMENTO_DADOS = "consentimento_dados"    

class EvaluationPhase(str, enum.Enum):
    """As seis fases do ciclo de avaliação (secção 3.1)."""
    AUTOAVALIACAO = "autoavaliacao"
    AVALIACAO_DIRECTOR = "avaliacao_director"
    CONCORDANCIA = "concordancia"
    COMISSAO = "comissao"
    FECHADA = "fechada"
    VALIDADA = "validada"


class EvaluationCategory(str, enum.Enum):
    """Categoria para efeitos de ponderação (secção 3.2)."""
    TECNICO = "tecnico"
    DIRIGENTE = "dirigente"    

class DisciplinaryPhase(str, enum.Enum):
    """As seis fases do processo disciplinar (secção 4.1)."""
    INSTAURACAO = "instauracao"
    NOTA_CULPA = "nota_culpa"
    DEFESA = "defesa"
    DECISAO = "decisao"
    CONHECIMENTO_DECISAO = "conhecimento_decisao"
    ARQUIVADO = "arquivado"


class DisciplinaryOutcome(str, enum.Enum):
    """Resultado da decisão (fase 4)."""
    PENDENTE = "pendente"
    ARQUIVAMENTO = "arquivamento"
    REPREENSAO = "repreensao"
    SUSPENSAO = "suspensao"
    DESPEDIMENTO = "despedimento"    

class TrainingSource(str, enum.Enum):
    """Origem da necessidade formativa (secção 5)."""
    SISTEMA = "sistema"
    AREA = "area"


class TrainingPlanStatus(str, enum.Enum):
    """Estado do plano de formação."""
    RASCUNHO = "rascunho"
    SUBMETIDO = "submetido"
    APROVADO = "aprovado"
    EM_EXECUCAO = "em_execucao"


class TrainingActionStatus(str, enum.Enum):
    """Estado de cada ação de formação."""
    PROPOSTA = "proposta"
    APROVADA = "aprovada"
    CONCLUIDA = "concluida"    

class SurveyStatus(str, enum.Enum):
    """Estado de um inquérito-pulso (secção 6)."""
    ABERTO = "aberto"
    FECHADO = "fechado"    

class FitnessResult(str, enum.Enum):
    """Resultado de aptidão do exame de medicina no trabalho (secção 2.7).
    NOTA: só aptidão — nunca diagnóstico ou dados clínicos."""
    APTO = "apto"
    APTO_COM_RESTRICOES = "apto_com_restricoes"
    INAPTO = "inapto"    

class CareerEventType(str, enum.Enum):
    """Tipos de evento manual do percurso (secção 2.3)."""
    LOUVOR = "louvor"
    NOMEACAO = "nomeacao"
    PROMOCAO = "promocao"
    OUTRO = "outro"    