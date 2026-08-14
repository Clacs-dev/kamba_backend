"""
Configuração central do KAMBA.

Todas as definições sensíveis (chaves, ligação à base de dados) vêm de
variáveis de ambiente / ficheiro .env — nunca escritas no código.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Identidade da aplicação ---
    APP_NAME: str = "KAMBA"
    APP_VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = True

    # --- Base de dados ---
    # SQLite para desenvolvimento. Para migrar para Postgres, basta trocar
    # esta variável no .env, ex.:
    #   DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/kamba
    DATABASE_URL: str = "sqlite:///./kamba.db"

    # --- Segurança / JWT ---
    # OBRIGATÓRIO definir SECRET_KEY no .env em produção.
    SECRET_KEY: str = "CHANGE-ME-em-producao-usa-uma-chave-aleatoria-longa"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 8  # 8 horas

    # --- CORS ---
    # Origens do frontend autorizadas a chamar a API.
    # Em produção, substituir pelo domínio real do frontend.
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ]

    # --- Catálogo CLACS Academy (secção 5) ---
    # URL público do catálogo; se vazio, a UI mostra que falta configurar.
    CLACS_ACADEMY_URL: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
