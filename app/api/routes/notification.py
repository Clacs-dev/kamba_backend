"""
Rotas de notificações.

O utilizador vê as suas próprias notificações (a "caixa de entrada"), sabe
quantas tem por ler (para o badge do frontend, consultado por polling) e
pode marcá-las como lidas.

As notificações são sempre do próprio utilizador autenticado — nunca de
outro — o que garante o isolamento naturalmente.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.models.notification import Notification
from app.schemas.notification import NotificationOut, UnreadCount
from app.api.deps import get_current_user

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationOut])
def list_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    only_unread: bool = Query(default=False, description="Apenas as não lidas"),
):
    """Lista as notificações do utilizador (mais recentes primeiro)."""
    query = db.query(Notification).filter(Notification.user_id == current_user.id)
    if only_unread:
        query = query.filter(Notification.is_read == False)  # noqa: E712
    return query.order_by(Notification.created_at.desc()).all()


@router.get("/unread-count", response_model=UnreadCount)
def unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Devolve o número de notificações por ler (para o badge; usado no polling)."""
    n = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id, Notification.is_read == False)  # noqa: E712
        .count()
    )
    return UnreadCount(unread=n)


@router.post("/{notification_id}/read", response_model=NotificationOut)
def mark_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Marca uma notificação como lida."""
    n = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == current_user.id)
        .first()
    )
    if n is None:
        raise HTTPException(status_code=404, detail="Notificação não encontrada.")
    n.is_read = True
    db.commit()
    db.refresh(n)
    return n


@router.post("/read-all", response_model=UnreadCount)
def mark_all_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Marca todas as notificações do utilizador como lidas."""
    (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id, Notification.is_read == False)  # noqa: E712
        .update({Notification.is_read: True})
    )
    db.commit()
    return UnreadCount(unread=0)
