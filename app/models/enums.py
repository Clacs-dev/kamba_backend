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
    EFETIVO = "efetivo"                    # contrato por tempo indeterminado
    TERMO_CERTO = "termo_certo"            # contrato a termo certo
    TERMO_INCERTO = "termo_incerto"        # contrato a termo incerto
    ESTAGIO = "estagio"                    # contrato de estágio
    PRESTACAO_SERVICOS = "prestacao_servicos"  # prestação de serviços


class DocumentType(str, enum.Enum):
    """Tipos de documento do dossier individual (secção 2.4)."""
    CONTRATO = "contrato"                        # contrato de trabalho
    REGULAMENTO_INTERNO = "regulamento_interno"
    CODIGO_ETICA = "codigo_etica"
    POLITICA_ASSIDUIDADE = "politica_assiduidade"
    POLITICA_REMUNERACAO = "politica_remuneracao"
    REGULAMENTO_AVALIACAO = "regulamento_avaliacao"
    OUTRO = "outro"


class SignatureType(str, enum.Enum):
    """As três assinaturas digitais de adesão (secção 2.2)."""
    REGULAMENTO_POLITICAS = "regulamento_politicas"  # adesão ao regulamento e políticas
    TERMOS_PORTAL = "termos_portal"                  # aceitação dos termos do portal
    CONSENTIMENTO_DADOS = "consentimento_dados"      # consentimento Lei 22/11


class EvaluationPhase(str, enum.Enum):
    """As seis fases do ciclo de avaliação (secção 3.1)."""
    AUTOAVALIACAO = "autoavaliacao"        # 1. Colaborador responde e submete
    AVALIACAO_DIRECTOR = "avaliacao_director"  # 2. Director avalia
    CONCORDANCIA = "concordancia"          # 3. Colaborador aceita ou recorre
    COMISSAO = "comissao"                  # 4. Comissão decide o recurso
    FECHADA = "fechada"                    # 5. Consolidada
    VALIDADA = "validada"                  # 6. Administração valida


class EvaluationCategory(str, enum.Enum):
    """Categoria para efeitos de ponderação (secção 3.2)."""
    TECNICO = "tecnico"        # objetivos 50%, competências 35%, valores 15%
    DIRIGENTE = "dirigente"    # resultados 60%, liderança 25%, valores 15%


class DisciplinaryPhase(str, enum.Enum):
    """As seis fases do processo disciplinar (secção 4.1)."""
    INSTAURACAO = "instauracao"                    # 1. abertura
    NOTA_CULPA = "nota_culpa"                       # 2. nota de culpa notificada
    DEFESA = "defesa"                               # 3. defesa recebida
    DECISAO = "decisao"                             # 4. decisão emitida
    CONHECIMENTO_DECISAO = "conhecimento_decisao"   # 5. tomada de conhecimento
    ARQUIVADO = "arquivado"                         # 6. concluído / arquivado


class DisciplinaryOutcome(str, enum.Enum):
    """Resultado da decisão (fase 4)."""
    PENDENTE = "pendente"
    ARQUIVAMENTO = "arquivamento"      # sem medida
    REPREENSAO = "repreensao"
    SUSPENSAO = "suspensao"
    DESPEDIMENTO = "despedimento"


class TrainingSource(str, enum.Enum):
    """Origem da necessidade formativa (secção 5)."""
    SISTEMA = "sistema"    # identificada automaticamente (nota < 3,5)
    AREA = "area"          # indicada por Director / Capital Humano


class TrainingPlanStatus(str, enum.Enum):
    """Estado do plano de formação."""
    RASCUNHO = "rascunho"        # em consolidação
    SUBMETIDO = "submetido"      # submetido à Administração
    APROVADO = "aprovado"        # aprovado pela Administração -> execução
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
    NOMEACAO = "nomeacao"          # nomeação para comissão de trabalho
    PROMOCAO = "promocao"
    OUTRO = "outro"
