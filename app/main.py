"""
Ponto de entrada da aplicação KAMBA.

Arranque:
    uvicorn app.main:app --reload --port 8000
Documentação interactiva:
    http://127.0.0.1:8000/docs
"""
import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func

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
from app.models.company import Company
from app.models.user import User


def _setup_database() -> None:
    # Cria as tabelas no SQLite se ainda não existirem.
    Base.metadata.create_all(bind=engine)
    # Acrescenta colunas novas que os modelos ganharam depois de a BD ser criada
    # (create_all não altera tabelas existentes).
    ensure_schema_columns()
    # Backfills idempotentes de dados para bases já existentes.
    backfill_survey_recommend_dimension()
    backfill_employee_numbers()


def _alvo_da_semente() -> str | None:
    """
    Decide a empresa a enriquecer no arranque:
      1. DEEP_SEED_COMPANY, se estiver definido (nome ou ID);
      2. senão, se existir DEMO_PASSWORD (ambiente de demonstração), a empresa que
         já tem mais utilizadores — que é a de demonstração;
      3. senão, nada (aplicação normal, sem dados artificiais).
    """
    alvo = (getattr(settings, "DEEP_SEED_COMPANY", None) or "").strip()
    if alvo:
        return alvo
    password = os.getenv("DEMO_PASSWORD") or getattr(settings, "DEEP_SEED_PASSWORD", None)
    if not password:
        return None
    with SessionLocal() as db:
        empresa = (
            db.query(Company)
            .join(User, User.company_id == Company.id)
            .group_by(Company.id)
            .order_by(func.count(User.id).desc(), Company.id)
            .first()
        )
        return str(empresa.id) if empresa else None


def _semente_de_demonstracao() -> None:
    """
    Enriquece a empresa alvo com o pacote completo de dados de demonstração.
    É idempotente, por isso pode ficar sempre ligado em ambientes de
    demonstração sem duplicar nada a cada arranque.
    """
    alvo = _alvo_da_semente()
    if not alvo:
        return
    try:
        from app.seed_deep import semear_por_nome

        semear_por_nome(
            alvo,
            password=os.getenv("DEMO_PASSWORD") or getattr(settings, "DEEP_SEED_PASSWORD", None),
            criar_se_nao_existir=bool(getattr(settings, "DEEP_SEED_COMPANY", None)),
        )
    except Exception as e:  # a aplicação tem de arrancar mesmo se a semente falhar
        print(f"[semente] erro ao semear '{alvo}': {e}")


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
    _semente_de_demonstracao()
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
