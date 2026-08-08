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
_is_sqlite = settings.DATABASE_URL.startswith("sqlite")
_connect_args = {"check_same_thread": False} if _is_sqlite else {}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=_connect_args,
    echo=False,  # coloca True para ver o SQL gerado durante o desenvolvimento
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
