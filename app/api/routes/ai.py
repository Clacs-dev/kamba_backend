"""
Rotas de IA — universidades e cursos por país.

Usa Google Gemini quando disponível; caso contrário, devolve listas estáticas
pré-definidas (fallback).
"""
import json
import logging
import threading
import time
from typing import Optional

import google.generativeai as genai
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.api.deps import get_current_user

log = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["ai"])


# ---------------------------------------------------------------------------
# Listas estáticas por país (fallback quando a IA não está disponível)
# ---------------------------------------------------------------------------

UNIVERSITIES: dict[str, list[str]] = {
    "Angola": [
        "Universidade Agostinho Neto (UAN)",
        "Universidade Católica de Angola (UCAN)",
        "Universidade Jean Piaget de Angola (UP)",
        "ISPTEC — Instituto Superior Politécnico de Tecnologias e Ciências",
        "ISCTEL — Instituto Superior de Ciências de Telecomunicações",
        "Instituto Superior de Ciências da Educação de Luanda (ISCED-Luanda)",
        "Universidade Lusíada de Angola",
        "Universidade Lusófona de Angola",
        "Universidade Metodista de Angola",
        "Universidade de Belas",
        "Universidade Mandume Ya Ndemufayo",
        "Universidade Katyavala Bwila",
        "Universidade Kimpa Vita",
        "Universidade Jose Eduardo dos Santos (UJES)",
        "Universidade Cuito Cuanavale",
        "Universidade Norberto de Teixeira",
        "ISPGaya — Instituto Superior Politécnico Geral Teixeira Pinto",
        "IAV — Instituto Angolano do Petróleo",
    ],
    "Moçambique": [
        "Universidade Eduardo Mondlane (UEM)",
        "Universidade Politécnica (UP)",
        "Universidade Católica de Moçambique (UCM)",
        "Universidade Lusíada de Moçambique",
        "Universidade São Tomás de Moçambique",
        "ISPU — Instituto Superior Politécnico de UniLúrio",
        "ISCTEM — Instituto Superior de Ciências e Tecnologia de Moçambique",
        "Universidade Zambeze (UniZambeze)",
        "Universidade Europa de Maputo",
        "ISPTEC Moçambique",
    ],
    "Portugal": [
        "Universidade de Lisboa (ULisboa)",
        "Universidade do Porto (UPorto)",
        "Universidade de Coimbra (UC)",
        "Universidade Nova de Lisboa (UNL)",
        "Universidade de Aveiro (UAveiro)",
        "Universidade do Minho (UMinho)",
        "Universidade de Évora (UEvora)",
        "Universidade do Algarve (UAlg)",
        "ISCTE — Instituto Universitário de Lisboa",
        "Instituto Superior Técnico (IST)",
        "Universidade Católica Portuguesa (UCP)",
        "Universidade de Trás-os-Montes e Alto Douro (UTAD)",
        "Universidade da Beira Interior (UBI)",
        "Universidade Lusíada — Porto / Lisboa",
        "Universidade Europeia",
    ],
    "Brasil": [
        "Universidade de São Paulo (USP)",
        "Universidade Estadual de Campinas (UNICAMP)",
        "Universidade Federal do Rio de Janeiro (UFRJ)",
        "Universidade de Brasília (UnB)",
        "Universidade Federal de Minas Gerais (UFMG)",
        "Universidade Federal do Paraná (UFPR)",
        "Universidade Federal do Rio Grande do Sul (UFRGS)",
        "Pontifícia Universidade Católica do Rio de Janeiro (PUC-Rio)",
        "Fundação Getulio Vargas (FGV)",
        "Universidade de Fortaleza (UNIFOR)",
        "Universidade Federal do Ceará (UFC)",
        "Universidade Federal de São Paulo (UNIFESP)",
    ],
    "Cabo Verde": [
        "Universidade de Cabo Verde (UNICV)",
        "ISPA — Instituto Superior Politécnico e Arts",
        "Universidade Jean Piaget de Cabo Verde",
    ],
    "Guiné-Bissau": [
        "Universidade Amílcar Cabral",
        "Instituto Superior de Ciências da Saúde (ISCS)",
    ],
    "São Tomé e Príncipe": [
        "Universidade de São Tomé e Príncipe (USTP)",
    ],
    "Timor-Leste": [
        "Universidade Nacional Timor Lorosa'e (UNTL)",
        "Universidade Católica de Timor-Leste (UCTL)",
    ],
    "Botsuana": [
        "University of Botswana",
        "Botswana International University of Science & Technology (BIUST)",
    ],
    "Namíbia": [
        "University of Namibia (UNAM)",
        "Namibia University of Science and Technology (NUST)",
    ],
    "África do Sul": [
        "University of Cape Town (UCT)",
        "University of the Witwatersrand (Wits)",
        "Stellenbosch University",
        "University of Pretoria (UP)",
        "University of Johannesburg (UJ)",
        "UNISA — University of South Africa",
        "Durban University of Technology (DUT)",
    ],
    "Nigéria": [
        "University of Lagos (UNILAG)",
        "University of Ibadan (UI)",
        "Obafemi Awolowo University (OAU)",
        "Ahmadu Bello University (ABU)",
        "University of Nigeria, Nsukka (UNN)",
        "Covenant University",
    ],
    "RD Congo": [
        "Université de Kinshasa (UNIKIN)",
        "Université de Lubumbashi (UNILU)",
        "Université Officielle de Bukavu (UNIBUKA)",
    ],
}


GEMINI_MODEL = "gemini-3.6-flash"

# Cache em memória para evitar chamadas repetidas à IA (a 1.ª é lenta).
_CACHE: dict[str, tuple[float, list[str]]] = {}
_CACHE_TTL = 24 * 3600  # 24h


def _cache_get(key: str) -> Optional[list[str]]:
    entry = _CACHE.get(key)
    if not entry:
        return None
    ts, value = entry
    if time.time() - ts > _CACHE_TTL:
        _CACHE.pop(key, None)
        return None
    return value


def _cache_set(key: str, value: list[str]) -> None:
    _CACHE[key] = (time.time(), value)


def _warm_cache_async(key: str, fetch):
    """Busca dados na IA em segundo plano e guarda no cache."""
    try:
        result = fetch()
        if result:
            _cache_set(key, result)
            log.info("[AI] cache atualizado para %s (%d itens)", key, len(result))
    except Exception as e:
        log.info("[AI] falha ao atualizar cache %s: %s", key, e)


def _get_model():
    """Configura e devolve o modelo Gemini. Levanta 503 se não houver chave."""
    if not settings.GEMINI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail=(
                "Chave da API Gemini não configurada. Adicione GEMINI_API_KEY "
                "ao .env e reinicie o backend."
            ),
        )
    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel(GEMINI_MODEL)
    return model


def _extract_json(text: str) -> Optional[list]:
    try:
        if "[" in text:
            start = text.index("[")
            end = text.rindex("]") + 1
            return json.loads(text[start:end])
        return json.loads(text)
    except Exception:
        return None


def _try_ai_universities(country: str) -> Optional[list[str]]:
    """Tenta buscar universidades via Gemini. Devolve None se falhar."""
    try:
        model = _get_model()
        prompt = (
            f"Cria uma lista EXAUSTIVA de universidades e instituições de ensino "
            f"superior de {country} (todos os nomes de que te lembrares, até 120), "
            f"COM nomes curtos (ex.: Universidade, ISPTEC). "
            f"Responde APENAS com um JSON array de strings, sem texto adicional."
        )
        resp = model.generate_content(prompt)
        data = _extract_json(resp.text)
        if data is None:
            return None
        return [str(x) for x in data]
    except Exception as e:
        log.info("[AI] Gemini indisponível para universidades (%s), usando lista estática.", e)
        return None


def _try_ai_courses(university: str, country: str) -> Optional[list[str]]:
    """Tenta buscar cursos via Gemini. Devolve None se falhar."""
    try:
        model = _get_model()
        prompt = (
            f"Cria uma lista EXAUSTIVA de cursos (licenciatura, mestrado, doutoramento) "
            f"oferecidos por \"{university}\" em {country} (até 120). "
            f"Usa APENAS o nome curto do curso, sem prefixos como 'Licenciatura em' (ex.: Engenharia Informática, Direito). "
            f"Responde APENAS com um JSON array de strings, sem texto adicional."
        )
        resp = model.generate_content(prompt)
        data = _extract_json(resp.text)
        if data is None:
            return None
        return [str(x) for x in data]
    except Exception as e:
        log.info("[AI] Gemini indisponível para cursos (%s), usando lista estática.", e)
        return None


# ---------------------------------------------------------------------------
# Listas estáticas de cursos genéricos por país
# ---------------------------------------------------------------------------

JOB_TITLES_STATIC: list[str] = [
    "Desenvolvedor Web", "Desenvolvedor Mobile", "Engenheiro de Software",
    "Analista de Sistemas", "Administrador de Redes", "Especialista em Segurança Informática",
    "Gestor de Projetos", "Gestor de Recursos Humanos", "Gestor Financeiro",
    "Contabilista", "Técnico de Contabilidade", "Economista", "Auditor",
    "Jurista", "Advogado", "Assistente Jurídico",
    "Médico", "Enfermeiro", "Técnico de Análises Clínicas", "Farmacêutico",
    "Professor", "Formador", "Assistente Administrativo",
    "Secretário(a) Executivo(a)", "Técnico Administrativo", "Rececionista",
    "Gestor Comercial", "Vendedor(a)", "Técnico de Marketing", "Designer Gráfico",
    "Comunicador Social", "Jornalista", "Publicitário",
    "Motorista", "Operador de Armazém", "Técnico de Manutenção",
    "Técnico Electrotécnico", "Mecânico", "Soldador", "Serralheiro",
    "Pedreiro", "Carpinteiro", "Eletricista", "Canalizador", "Pintor",
    "Operador de Caixa", "Repositor(a)", "Segurança", "Porteiro",
    "Técnico de Apoio Informático", "Analista de Dados", "Gestor de Operações",
    "Supervisor de Produção", "Logística", "Técnico de Compras", "Auxiliar de Serviços Gerais",
]

# Todos os países do mundo (português) — fallback instantâneo; a IA refina via cache.
COUNTRIES_STATIC: list[str] = [
    "Afeganistão", "África do Sul", "Albânia", "Alemanha", "Andorra", "Angola",
    "Antígua e Barbuda", "Arábia Saudita", "Argélia", "Argentina", "Arménia",
    "Austrália", "Áustria", "Azerbaijão", "Bahamas", "Bangladexe", "Barbados",
    "Barém", "Bélgica", "Belize", "Benim", "Bielorrússia", "Bolívia",
    "Bósnia e Herzegovina", "Botsuana", "Brasil", "Brunei", "Bulgária",
    "Burkina Faso", "Burundi", "Butão", "Cabo Verde", "Camarões", "Camboja",
    "Canadá", "Cazaquistão", "Chade", "Chile", "China", "Chipre", "Colômbia",
    "Comores", "Coreia do Norte", "Coreia do Sul", "Costa do Marfim",
    "Costa Rica", "Croácia", "Cuba", "Dinamarca", "Djibuti", "Dominica",
    "Egito", "El Salvador", "Emirados Árabes Unidos", "Equador", "Eritreia",
    "Eslováquia", "Eslovénia", "Espanha", "Estados Unidos", "Estónia",
    "Etiópia", "Fiji", "Filipinas", "Finlândia", "França", "Gabão", "Gâmbia",
    "Gana", "Geórgia", "Granada", "Grécia", "Guatemala", "Guiana", "Guiné",
    "Guiné-Bissau", "Guiné Equatorial", "Haiti", "Honduras", "Hungria",
    "Iémen", "Ilhas Maurícias", "Índia", "Indonésia", "Irão", "Iraque",
    "Irlanda", "Islândia", "Israel", "Itália", "Jamaica", "Japão", "Jordânia",
    "Kuwait", "Laos", "Lesoto", "Letónia", "Líbano", "Libéria", "Líbia",
    "Listenstaine", "Lituânia", "Luxemburgo", "Macedónia do Norte",
    "Madagáscar", "Malásia", "Malawi", "Maldivas", "Mali", "Malta", "Marrocos",
    "Mauritânia", "México", "Mianmar", "Moçambique", "Moldávia", "Mónaco",
    "Mongólia", "Montenegro", "Namíbia", "Nauru", "Nepal", "Nicarágua",
    "Níger", "Nigéria", "Noruega", "Nova Zelândia", "Omã", "Países Baixos",
    "Palau", "Panamá", "Papua-Nova Guiné", "Paquistão", "Paraguai", "Peru",
    "Polónia", "Portugal", "Qatar", "Quénia", "Quirguistão", "Quiribáti",
    "Reino Unido", "República Centro-Africana", "República Checa",
    "República do Congo", "República Dominicana", "RD Congo", "Roménia",
    "Ruanda", "Rússia", "Salomão", "Samoa", "San Marino", "Santa Lúcia",
    "São Cristóvão e Nevis", "São Tomé e Príncipe", "São Vicente e Granadinas",
    "Seicheles", "Senegal", "Serra Leoa", "Sérvia", "Singapura", "Síria",
    "Somália", "Sri Lanca", "Sudão", "Sudão do Sul", "Suécia", "Suíça",
    "Suriname", "Tailândia", "Taiwan", "Tajiquistão", "Tanzânia",
    "Timor-Leste", "Togo", "Tonga", "Trindade e Tobago", "Tunísia",
    "Turquemenistão", "Turquia", "Tuvalu", "Ucrânia", "Uganda", "Uruguai",
    "Usbequistão", "Vanuatu", "Vaticano", "Venezuela", "Vietname", "Zâmbia",
    "Zimbabué",
]

COURSES_BY_COUNTRY: dict[str, list[str]] = {
    "Angola": [
        "Engenharia Informática", "Engenharia Civil", "Engenharia Electrotécnica",
        "Medicina", "Direito", "Gestão", "Economia", "Contabilidade",
        "Enfermagem", "Farmácia", "Arquitectura", "Educação",
        "Jornalismo e Comunicação", "Matemática", "Física",
        "Turismo e Hotelaria", "Agronomia", "Veterinária",
    ],
    "Portugal": [
        "Engenharia Informática", "Engenharia Civil", "Medicina",
        "Direito", "Gestão", "Economia", "Contabilidade",
        "Arquitectura", "Psicologia", "Enfermagem", "Farmácia",
        "Design", "Marketing", "Jornalismo",
    ],
    "Brasil": [
        "Engenharia Civil", "Engenharia de Software", "Direito",
        "Medicina", "Administração", "Contabilidade", "Enfermagem",
        "Odontologia", "Psicologia", "Arquitetura", "Educação Física",
        "Jornalismo", "Publicidade e Propaganda",
    ],
}


def _try_ai_countries() -> Optional[list[str]]:
    """Tenta buscar a lista de todos os países do mundo via Gemini."""
    try:
        model = _get_model()
        prompt = (
            f"Cria uma lista EXAUSTIVA de todos os países e territórios independentes do mundo, "
            f"em português, TODOS (aproximadamente 195). Nomes curtos e comuns "
            f"(ex.: Angola, França, México). "
            f"Responde APENAS com um JSON array de strings, sem texto adicional."
        )
        resp = model.generate_content(prompt)
        data = _extract_json(resp.text)
        if data is None:
            return None
        return [str(x) for x in data]
    except Exception as e:
        log.info("[AI] Gemini indisponível para países (%s), usando lista estática.", e)
        return None


def _try_ai_job_titles() -> Optional[list[str]]:
    """Tenta buscar cargos/funções via Gemini. Devolve None se falhar."""
    try:
        model = _get_model()
        prompt = (
            f"Cria uma lista EXAUSTIVA de cargos e funções profissionais comuns "
            f"(ex.: Desenvolvedor Web, Gestor de RH, Contabilista, Enfermeiro, "
            f"Motorista, Segurança...), em português, até 150. "
            f"Nomes curtos. Responde APENAS com um JSON array de strings, "
            f"sem texto adicional."
        )
        resp = model.generate_content(prompt)
        data = _extract_json(resp.text)
        if data is None:
            return None
        return [str(x) for x in data]
    except Exception as e:
        log.info("[AI] Gemini indisponível para cargos (%s), usando lista estática.", e)
        return None


class JobTitlesRequest(BaseModel):
    pass


class UniversitiesRequest(BaseModel):
    country: str


class CoursesRequest(BaseModel):
    university: str
    country: str


@router.post("/countries")
def list_countries(
    payload: JobTitlesRequest,
    _user: object = Depends(get_current_user),
) -> list[str]:
    """
    Devolve a lista de todos os países do mundo.
    Lista estática imediata; a IA refine e atualiza o cache em segundo plano.
    """
    key = "paises"
    cached = _cache_get(key)
    if cached is not None:
        return cached

    threading.Thread(
        target=_warm_cache_async,
        args=(key, _try_ai_countries),
        daemon=True,
    ).start()
    return COUNTRIES_STATIC


@router.post("/job-titles")
def list_job_titles(
    payload: JobTitlesRequest,
    _user: object = Depends(get_current_user),
) -> list[str]:
    """
    Devolve a lista de cargos/funções profissionais.
    Tenta IA primeiro; caso contrário, usa a lista estática.
    """
    key = "cargos"
    cached = _cache_get(key)
    if cached is not None:
        return cached

    # Resposta imediata com a lista estática; a IA atualiza o cache em segundo plano.
    threading.Thread(
        target=_warm_cache_async,
        args=(key, _try_ai_job_titles),
        daemon=True,
    ).start()
    return JOB_TITLES_STATIC


@router.post("/universities")
def list_universities(
    payload: UniversitiesRequest,
    _user: object = Depends(get_current_user),
) -> list[str]:
    """
    Devolve a lista de universidades de um país.
    Tenta IA primeiro; se falhar, usa lista estática.
    """
    if not payload.country.strip():
        return []

    key = f"uni:{payload.country.strip().lower()}"
    cached = _cache_get(key)
    if cached is not None:
        return cached

    estatica = UNIVERSITIES.get(payload.country, [])
    if estatica:
        # Resposta imediata com a lista estática; a IA atualiza o cache em segundo plano.
        threading.Thread(
            target=_warm_cache_async,
            args=(key, lambda c=payload.country.strip(): _try_ai_universities(c)),
            daemon=True,
        ).start()
        return estatica

    # País sem lista estática: chama a IA de imediato (regressa com dados completos).
    ai_result = _try_ai_universities(payload.country)
    if ai_result:
        _cache_set(key, ai_result)
    return ai_result or []


@router.post("/courses")
def list_courses(
    payload: CoursesRequest,
    _user: object = Depends(get_current_user),
) -> list[str]:
    """
    Devolve a lista de cursos de uma universidade.
    Tenta IA primeiro; se falhar, usa lista estática genérica do país.
    """
    if not payload.university.strip():
        return []

    key = "crs:%s|%s" % (
        payload.university.strip().lower(),
        payload.country.strip().lower(),
    )
    cached = _cache_get(key)
    if cached is not None:
        return cached

    # Resposta imediata com a lista genérica do país; a IA atualiza em segundo plano.
    estatica = COURSES_BY_COUNTRY.get(payload.country, [])
    if estatica:
        # Resposta imediata com a lista genérica do país; a IA atualiza em segundo plano.
        threading.Thread(
            target=_warm_cache_async,
            args=(
                key,
                lambda u=payload.university.strip(), c=payload.country.strip(): (
                    _try_ai_courses(u, c)
                ),
            ),
            daemon=True,
        ).start()
        return estatica

    # País sem cursos genéricos: chama a IA de imediato.
    ai_result = _try_ai_courses(payload.university, payload.country)
    if ai_result:
        _cache_set(key, ai_result)
    return ai_result or []
