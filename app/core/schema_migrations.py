"""
Mini-migração de arranque (substituto temporário de Alembic).

Base.metadata.create_all() apenas cria tabelas em falta e nunca altera
tabelas existentes. Quando um modelo ganha uma coluna nova, bases criadas
antes ficam sem ela, e qualquer leitura/escrita dessa coluna rebenta com
erro SQL (ex.: employee_profiles.job_title, leave_requests.rejection_reason).

Este módulo compara as colunas de cada modelo com as colunas reais da base
e acrescenta as que faltam (ALTER TABLE ADD COLUMN), de forma idempotente.
Funciona em SQLite e PostgreSQL. Em produção devemos migrar para Alembic.

Também inclui backfills de dados idempotentes para bases já existentes
(ex.: adicionar a pergunta de recomendação aos pulses abertos, para o
eNPS passar a ser calculado).
"""
import json

from sqlalchemy import inspect, text

from app.core.database import Base, engine


def _column_type(column) -> str:
    return column.type.compile(engine.dialect)


def ensure_schema_columns() -> None:
    """Acrescenta às tabelas existentes as colunas que os modelos já definem."""
    try:
        inspector = inspect(engine)
    except Exception:
        return

    db_tables = set(inspector.get_table_names())
    missing: list[tuple[str, str, str]] = []
    for table in Base.metadata.sorted_tables:
        if table.name not in db_tables:
            continue
        db_cols = {c["name"] for c in inspector.get_columns(table.name)}
        for col in table.columns:
            if col.name not in db_cols:
                missing.append((table.name, col.name, _column_type(col)))

    if not missing:
        return

    with engine.begin() as conn:
        for table_name, col_name, col_type in missing:
            try:
                conn.execute(
                    text(f'ALTER TABLE {table_name} ADD COLUMN "{col_name}" {col_type}')
                )
            except Exception:
                # Coluna entretanto criada (ou bloqueio): avança para a seguinte.
                pass


RECOMMEND_QUESTION = "Recomendaria a empresa como um bom lugar para trabalhar"
RECOMMEND_KEYWORDS = ("recomend", "recommend")


def backfill_employee_numbers() -> None:
    """
    Backfill idempotente: dá número mecanográfico (sequencial, 4 dígitos) aos
    colaboradores cujas fichas ficaram sem número (criados antes desta regra).
    Mantém a unicidade por empresa.
    """
    try:
        from app.core.database import SessionLocal
        from app.models.employee_profile import EmployeeProfile
    except Exception:
        return

    with SessionLocal() as db:
        perfis = (
            db.query(EmployeeProfile)
            .filter(EmployeeProfile.employee_number.is_(None))
            .all()
        )
        if not perfis:
            return

        # Maior número já atribuído por empresa.
        maiores: dict[int, int] = {}
        for (company_id, num) in (
            db.query(EmployeeProfile.company_id, EmployeeProfile.employee_number)
            .filter(EmployeeProfile.employee_number.isnot(None))
            .all()
        ):
            try:
                n = int(str(num).lstrip("0") or "0")
            except (ValueError, TypeError):
                continue
            maiores[company_id] = max(maiores.get(company_id, 0), n)

        atribuidos = 0
        for p in perfis:
            prox = maiores.get(p.company_id, 0) + 1
            maiores[p.company_id] = prox
            p.employee_number = f"{prox:04d}"
            atribuidos += 1
        db.commit()
        print(f"[migração] Número mecanográfico atribuído a {atribuidos} colaborador(es) sem número.")


def backfill_survey_recommend_dimension() -> None:
    """
    Backfill de dados: garante que os pulses ABERTOS incluem a pergunta de
    recomendação, de modo que o eNPS seja calculado automaticamente das
    respostas. Idempotente — não toca em pulses que já a têm nem em fechados.
    """
    try:
        from sqlalchemy.orm import Session  # noqa: F401

        from app.core.database import SessionLocal
        from app.models.enums import SurveyStatus
        from app.models.survey import Survey
    except Exception:
        return

    with SessionLocal() as db:
        surveys = (
            db.query(Survey)
            .filter(Survey.status == SurveyStatus.ABERTO)
            .all()
        )
        changed = 0
        for s in surveys:
            try:
                dims = json.loads(s.dimensions)
            except Exception:
                continue
            has_recommend = any(
                any(k in d.strip().lower() for k in RECOMMEND_KEYWORDS)
                for d in dims
            )
            if has_recommend:
                continue
            dims.append(RECOMMEND_QUESTION)
            s.dimensions = json.dumps(dims)
            changed += 1
        if changed:
            db.commit()
            print(f"[migração] Perca de recomendação adicionada a {changed} pulse(s) aberto(s).")
