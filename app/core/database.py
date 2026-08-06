"""
Camada de base de dados (SQLAlchemy 2.0).

Pensada para migrar de SQLite para Postgres sem alterar o resto do código:
tudo o que é específico do SQLite está isolado aqui.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session

from app.core.config import settings

# O argumento connect_args só é necessário para SQLite (permite usar a mesma
# ligação em várias threads do servidor). Ao migrar para Postgres, é ignorado.
# O Render fornece a ligação Postgres como "postgres://", mas o SQLAlchemy
# moderno exige "postgresql://". Corrige automaticamente. No local (SQLite),
# esta linha não tem efeito nenhum.
_db_url = settings.DATABASE_URL
if _db_url.startswith("postgres://"):
    _db_url = _db_url.replace("postgres://", "postgresql://", 1)

_is_sqlite = _db_url.startswith("sqlite")
_connect_args = {"check_same_thread": False} if _is_sqlite else {}

engine = create_engine(
    _db_url,
    connect_args=_connect_args,
    echo=False,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base declarativa de onde todos os modelos herdam.
Base = declarative_base()


def get_db():
    """
    Dependência do FastAPI: fornece uma sessão de base de dados por pedido
    e garante que é fechada no fim, mesmo que ocorra um erro.
    """
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
