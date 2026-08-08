"""
Serviço de notificações — função única para criar avisos.

Os módulos (avaliação, disciplina, formação...) chamam notify(...) nos
momentos-chave. Centralizar aqui evita repetir código e mantém o formato
consistente.

Nota: esta função adiciona a notificação à sessão mas NÃO faz commit — quem
chama já está numa transação e faz o commit no fim. Isto garante que a
notificação só existe se a ação principal também for gravada.
"""
from sqlalchemy.orm import Session

from app.models.notification import Notification


def notify(
    db: Session,
    *,
    company_id: int,
    user_id: int,
    title: str,
    message: str,
    category: str | None = None,
    link: str | None = None,
) -> Notification:
    n = Notification(
        company_id=company_id,
        user_id=user_id,
        title=title,
        message=message,
        category=category,
        link=link,
    )
    db.add(n)
    return n
