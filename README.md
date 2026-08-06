# KAMBA — Backend

Plataforma SaaS de Gestão de Capital Humano (avaliação de desempenho, processo
disciplinar, formação e cultura organizacional) para o mercado angolano.

Esta é a **fundação** do backend: autenticação multi-perfil e arquitectura
multi-empresa (multi-tenant). Os módulos de negócio serão construídos por cima
desta base.

## Como arrancar

```bash
# 1. Criar e activar o ambiente virtual
python -m venv venv
# Windows:
.\venv\Scripts\Activate.ps1
# Linux/Mac:
# source venv/bin/activate

# 2. Instalar dependências
pip install -r requirements.txt

# 3. Configurar variáveis de ambiente
#    Copia .env.example para .env e define uma SECRET_KEY real:
#    python -c "import secrets; print(secrets.token_urlsafe(64))"

# 4. Arrancar
uvicorn app.main:app --reload --port 8000
```

Documentação interactiva: http://127.0.0.1:8000/docs

## O que já funciona

- `POST /api/v1/auth/register` — regista uma empresa e o seu primeiro
  utilizador (perfil Capital Humano).
- `POST /api/v1/auth/login` — devolve um token JWT.
- `GET  /api/v1/auth/me` — devolve o utilizador autenticado (rota protegida).

## Arquitectura

```
app/
├── core/
│   ├── config.py      # configuração (lê do .env)
│   ├── database.py    # ligação SQLAlchemy (SQLite -> Postgres sem dor)
│   └── security.py    # hash de passwords (bcrypt) + tokens JWT
├── models/            # tabelas SQLAlchemy
│   ├── enums.py       # os cinco perfis do manual
│   ├── company.py     # o tenant (empresa)
│   └── user.py        # utilizador, ligado à empresa
├── schemas/           # contratos Pydantic (entrada/saída da API)
├── api/
│   ├── deps.py        # autenticação + controlo de acesso por perfil
│   └── routes/        # as rotas
└── main.py            # ponto de entrada + CORS
```

## Multi-tenancy (isolamento entre empresas)

Estratégia: **tenant por coluna**. Cada registo pertence a uma empresa via
`company_id`. O `company_id` é sempre imposto a partir do token do utilizador
autenticado — nunca de um parâmetro que o cliente possa manipular. É isto que
impede uma empresa de ver dados de outra.

## Migração para Postgres

Quando for altura, basta mudar `DATABASE_URL` no `.env` para uma string
Postgres e instalar `psycopg2-binary` (já comentado no requirements.txt).
Recomenda-se introduzir o **Alembic** para migrações antes de ir para produção,
em vez do `create_all` actual.

## Próximos passos sugeridos

1. Gestão de colaboradores (o Capital Humano cadastra utilizadores da empresa).
2. Portal do Colaborador (os nove separadores do manual).
3. Ciclo de avaliação de desempenho (máquina de estados de seis fases).
4. Processo disciplinar (seis fases, conforme a Lei Geral do Trabalho).
