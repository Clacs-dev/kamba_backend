"""
Mini-migração de arranque (substituto temporário de Alembic).

Base.metadata.create_all() apenas cria tabelas em falta e nunca altera
tabelas existentes. Quando um modelo ganha uma coluna nova, bases criadas
antes ficam sem ela, e qualquer leitura/escrita dessa coluna rebenta com
erro SQL (ex.: employee_profiles.job_title, leave_requests.rejection_reason).

Este módulo compara as colunas de cada modelo com as colunas reais da base
e acrescenta as que faltam (ALTER TABLE ADD COLUMN), de forma idempotente.
Funciona em SQLite e PostgreSQL. Em produção devemos migrar para Alembic.
"""
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
