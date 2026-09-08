"""
Rotas de chat directo entre utilizadores (alteração 7).

Sem infraestrutura de tempo real no projecto (nem WebSocket, nem SSE, nem
Socket.IO/Supabase Realtime — confirmado por análise ao código antes de
implementar esta alteração). O frontend consulta por polling, exactamente
como já faz `Notificacoes.tsx` com `GET /notifications/unread-count`.

Qualquer colaborador autenticado pode conversar com qualquer colega da MESMA
empresa — company_id vem sempre do token, nunca do cliente (regra de ouro
do projecto, ver collaborators.py).
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.models.chat import ChatMessage
from app.schemas.chat import MessageCreate, MessageOut, ConversationOut, UnreadCountOut, ColleagueOut
from app.api.deps import get_current_user

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("/colleagues", response_model=list[ColleagueOut])
def list_colleagues(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Colegas da mesma empresa disponíveis para iniciar uma conversa. Ao
    contrário de GET /collaborators (reservado a CH/Administração), esta
    lista é visível a qualquer utilizador autenticado — só o suficiente para
    escolher com quem falar (id, nome, perfil), sem dados de gestão de RH.
    """
    users = (
        db.query(User)
        .filter(
            User.company_id == current_user.company_id,
            User.is_active == True,  # noqa: E712
            User.id != current_user.id,
        )
        .order_by(User.full_name)
        .all()
    )
    return [
        ColleagueOut(id=u.id, full_name=u.full_name, role=u.role.value if hasattr(u.role, "value") else str(u.role))
        for u in users
    ]


def _get_company_user_or_404(db: Session, company_id: int, user_id: int) -> User:
    """Mesmo padrão de collaborators.py: nunca revela que o id existe noutra empresa."""
    user = (
        db.query(User)
        .filter(User.id == user_id, User.company_id == company_id)
        .first()
    )
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Colaborador não encontrado.")
    return user


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Lista os colegas com quem o utilizador já trocou mensagens, mais recentes
    primeiro, com a última mensagem e a contagem de não lidas de cada um.
    """
    msgs = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.company_id == current_user.company_id,
            or_(
                ChatMessage.sender_id == current_user.id,
                ChatMessage.recipient_id == current_user.id,
            ),
        )
        .order_by(ChatMessage.created_at.desc())
        .all()
    )

    por_correspondente: dict[int, dict] = {}
    for m in msgs:
        outro_id = m.recipient_id if m.sender_id == current_user.id else m.sender_id
        entrada = por_correspondente.setdefault(outro_id, {"ultima": m, "nao_lidas": 0})
        if m.recipient_id == current_user.id and not m.is_read:
            entrada["nao_lidas"] += 1

    if not por_correspondente:
        return []

    users = {
        u.id: u
        for u in db.query(User).filter(User.id.in_(por_correspondente.keys())).all()
    }

    linhas = []
    for outro_id, entrada in por_correspondente.items():
        u = users.get(outro_id)
        if u is None:
            continue  # colega entretanto removido — não aparece na lista
        m = entrada["ultima"]
        linhas.append(ConversationOut(
            user_id=outro_id,
            full_name=u.full_name,
            role=u.role.value if hasattr(u.role, "value") else str(u.role),
            last_message=m.body,
            last_message_at=m.created_at,
            unread_count=entrada["nao_lidas"],
        ))

    linhas.sort(key=lambda r: r.last_message_at, reverse=True)
    return linhas


@router.get("/unread-count", response_model=UnreadCountOut)
def unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Total de mensagens por ler do utilizador (badge, consultado por polling)."""
    n = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.company_id == current_user.company_id,
            ChatMessage.recipient_id == current_user.id,
            ChatMessage.is_read == False,  # noqa: E712
        )
        .count()
    )
    return UnreadCountOut(unread=n)


@router.get("/conversations/{user_id}/messages", response_model=list[MessageOut])
def get_conversation_messages(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=200),
    before_id: int | None = Query(default=None, description="Pagina mensagens anteriores a este id"),
):
    """
    Histórico com um colega (mais antigas primeiro, para render directo na
    thread). Marca como lidas as mensagens recebidas desse colega.
    """
    _get_company_user_or_404(db, current_user.company_id, user_id)

    query = db.query(ChatMessage).filter(
        ChatMessage.company_id == current_user.company_id,
        or_(
            (ChatMessage.sender_id == current_user.id) & (ChatMessage.recipient_id == user_id),
            (ChatMessage.sender_id == user_id) & (ChatMessage.recipient_id == current_user.id),
        ),
    )
    if before_id is not None:
        query = query.filter(ChatMessage.id < before_id)

    mensagens = query.order_by(ChatMessage.created_at.desc()).limit(limit).all()
    mensagens.reverse()  # devolve em ordem cronológica

    # Marca como lidas as que o utilizador recebeu deste colega.
    por_ler_ids = [m.id for m in mensagens if m.recipient_id == current_user.id and not m.is_read]
    if por_ler_ids:
        (
            db.query(ChatMessage)
            .filter(ChatMessage.id.in_(por_ler_ids))
            .update({ChatMessage.is_read: True}, synchronize_session=False)
        )
        db.commit()
        for m in mensagens:
            if m.id in por_ler_ids:
                m.is_read = True

    return mensagens


@router.post("/conversations/{user_id}/messages", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
def send_message(
    user_id: int,
    payload: MessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Envia uma mensagem a um colega da mesma empresa."""
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Não pode enviar uma mensagem a si próprio.")
    _get_company_user_or_404(db, current_user.company_id, user_id)

    message = ChatMessage(
        company_id=current_user.company_id,
        sender_id=current_user.id,
        recipient_id=user_id,
        body=payload.body,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message
