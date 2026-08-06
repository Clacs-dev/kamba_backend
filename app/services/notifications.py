"""
Serviço de notificações — função única para criar avisos.
Adiciona à sessão mas NÃO faz commit: quem chama faz o commit no fim.
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