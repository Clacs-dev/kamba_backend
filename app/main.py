"""
Ponto de entrada da aplicação KAMBA.

Arranque:
    uvicorn app.main:app --reload --port 8000
Documentação interactiva:
    http://127.0.0.1:8000/docs
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import Base, engine
from app.core.schema_migrations import ensure_schema_columns
from app.api.routes import api_router

# Importar os modelos garante que estão registados na Base ANTES de criar as
# tabelas. (Em produção passaremos a usar migrações Alembic em vez disto.)
from app.models import company, user, employee_profile, dossier, evaluation, disciplinary, training, development, survey, notification, occupational, compensation, career, culture_report, audit, onboarding, evaluation_settings, ficha_correction, leave, collaborator_document  # noqa: F401

# Cria as tabelas em SQLite se ainda não existirem.
Base.metadata.create_all(bind=engine)
# Acrescenta colunas novas que os modelos ganharam depois de a BD ser criada
# (create_all não altera tabelas existentes).
ensure_schema_columns()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Plataforma de Gestão de Capital Humano — KAMBA",
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
