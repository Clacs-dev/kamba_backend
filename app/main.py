"""
Ponto de entrada da aplicação KAMBA.

Arranque:
    uvicorn app.main:app --reload --port 8000
Documentação interactiva:
    http://127.0.0.1:8000/docs
"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import Base, engine, SessionLocal
from app.core.schema_migrations import (
    ensure_schema_columns,
    backfill_survey_recommend_dimension,
    backfill_employee_numbers,
)
from app.api.routes import api_router

# Importar os modelos garante que estão registados na Base ANTES de criar as
# tabelas. (Em produção passaremos a usar migrações Alembic em vez disto.)
from app.models import company, user, employee_profile, dossier, evaluation, disciplinary, training, development, survey, notification, occupational, compensation, career, culture_report, audit, onboarding, evaluation_settings, ficha_correction, leave, collaborator_document, shift, chat, talent  # noqa: F401
from app.models.organ import OrganMember  # noqa: F401


def _setup_database() -> None:
    # Cria as tabelas em SQLite se ainda não existirem.
    Base.metadata.create_all(bind=engine)
    # Acrescenta colunas novas que os modelos ganharam depois de a BD ser criada
    # (create_all não altera tabelas existentes).
    ensure_schema_columns()
    # Backfills idempotentes de dados para bases já existentes.
    backfill_survey_recommend_dimension()
    backfill_employee_numbers()


async def _agendar_aniversarios() -> None:
    """Corre o processamento de aniversários no arranque e de 6 em 6 horas."""
    from app.services.birthdays import processar_aniversarios

    while True:
        try:
            with SessionLocal() as db:
                emails, nots = processar_aniversarios(db)
                if emails or nots:
                    print(f"[aniversários] {emails} email(s), {nots} notificação(ões).")
        except Exception as e:
            print(f"[aniversários] erro: {e}")
        await asyncio.sleep(6 * 3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _setup_database()
    task = asyncio.create_task(_agendar_aniversarios())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Plataforma de Gestão de Capital Humano — KAMBA",
    lifespan=lifespan,
)

# CORS: permite que o frontend (noutra origem/porta) chame a API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=r"https://.*\.vercel\.app",  # permite o frontend no Vercel (incl. previews)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Todas as rotas ficam sob /api/v1
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/", tags=["default"])
def root():
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "online",
        "docs": "/docs",
    }
