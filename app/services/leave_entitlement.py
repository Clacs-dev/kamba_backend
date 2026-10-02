"""
Direito a férias por ano de férias (art. 209.º da LGT).

Regra adoptada: cada colaborador tem direito a 22 dias úteis de férias por cada
ano de férias, isto é, por cada período de 12 meses contado da sua data de
admissão. O mês de admissão é irrelevante — quem foi admitido no mês Y completa
um ano no mês Y do ano seguinte.

O mapa de férias é desenhado por ano-calendário, pelo que o direito atribuível a
um dado ano é a fracção dos 22 dias cujo ano de férias cai dentro desse ano-calendário.
Um ano de férias que atravessa a virada do ano contribui para os dois anos-calendário
adjacentes, de forma que a soma das contribuições dá sempre 22 dias por ano de férias.

Quem tem praticamente um ano de férias inteiro dentro do ano-calendário recebe os 22
integrais (ver FULL_YEAR_RATIO); quem foi admitido no próprio ano recebe apenas a parte
correspondente ao período que ainda decorre.

Exemplo: admissão a 2026-05-05 -> ano de férias 1 = 2026-05-05 a 2027-05-04.
No mapa de 2026 ficam ~14 dias e no de 2027 os ~8 dias restantes desse ano de férias
mais a parte do ano de férias 2 que decorre em 2027.
"""
from datetime import date, timedelta

ANNUAL_DAYS = 22

# Collaborator whose leave year covers at least this share of the calendar year's
# working days is considered to have a full year inside it -> full 22 days.
FULL_YEAR_RATIO = 0.90


def add_years(d: date, n: int) -> date:
    """Same day n years later; 29 Feb falls back to 28 Feb."""
    try:
        return d.replace(year=d.year + n)
    except ValueError:
        return d.replace(year=d.year + n, day=28)


def working_days(a: date, b: date) -> int:
    """Working days (Mon-Fri) in the inclusive range [a, b]; 0 when b < a."""
    if b < a:
        return 0
    total = 0
    d = a
    while d <= b:
        if d.weekday() < 5:
            total += 1
        d += timedelta(days=1)
    return total


def leave_year(admission: date, ref: date) -> tuple[date, date]:
    """[start, end] of the 12-month leave year that contains `ref`."""
    if ref < admission:
        return admission, add_years(admission, 1) - timedelta(days=1)
    k = 0
    while add_years(admission, k + 1) <= ref:
        k += 1
    inicio = add_years(admission, k)
    return inicio, add_years(inicio, 1) - timedelta(days=1)


def _round_half_up(x: float) -> int:
    return int(x + 0.5) if x >= 0 else 0


def entitlement_for_year(admission: date | None, ano: int) -> dict:
    """
    Entitlement attributable to calendar year `ano`.

    Returns dict with direito/gozados/marcados/disponiveis/pode_pedir plus the
    dominant leave-year bounds so the UI can explain the figure.
    """
    ini_ano = date(ano, 1, 1)
    fim_ano = date(ano, 12, 31)

    if admission is None:
        # Sem data de admissao na ficha: assume ano-calendario com direito integral.
        return {
            "direito": ANNUAL_DAYS,
            "gozados": 0,
            "marcados": 0,
            "em_curso": 0,
            "disponiveis": ANNUAL_DAYS,
            "pode_pedir": True,
            "fracao": 1.0,
            "ano_inicio": ini_ano.isoformat(),
            "ano_fim": fim_ano.isoformat(),
            "base": "ano_calendar",
        }

    fracao = 0.0
    melhor_wd = -1
    melhor_ini = admission
    melhor_fim = add_years(admission, 1) - timedelta(days=1)

    for k in range(0, 100):
        inicio = add_years(admission, k)
        if inicio > fim_ano:
            break
        fim = add_years(inicio, 1) - timedelta(days=1)
        wd_periodo = working_days(inicio, fim)
        if not wd_periodo:
            continue
        wd_parte = working_days(max(inicio, ini_ano), min(fim, fim_ano))
        if not wd_parte:
            continue
        fracao += wd_parte / wd_periodo
        if wd_parte > melhor_wd:
            melhor_wd, melhor_ini, melhor_fim = wd_parte, inicio, fim

    fracao = min(fracao, 1.0)
    direito = ANNUAL_DAYS if fracao >= FULL_YEAR_RATIO else _round_half_up(ANNUAL_DAYS * fracao)

    return {
        "direito": direito,
        "gozados": 0,
        "marcados": 0,
        "em_curso": 0,
        "disponiveis": direito,
        "pode_pedir": False,
        "fracao": round(fracao, 4),
        "ano_inicio": melhor_ini.isoformat(),
        "ano_fim": melhor_fim.isoformat(),
        "base": "ano_admissao",
    }


def finalise(dados: dict, gozados: int, marcados: int, em_curso: int = 0) -> dict:
    """Applies consumed/booked leave on top of `entitlement_for_year` output."""
    direito = dados["direito"]
    disponiveis = max(direito - gozados - marcados - em_curso, 0)
    dados.update(
        gozados=gozados,
        marcados=marcados,
        em_curso=em_curso,
        disponiveis=disponiveis,
        pode_pedir=direito > 0 and disponiveis > 0,
    )
    return dados