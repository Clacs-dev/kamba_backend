"""
Schemas Pydantic — chat directo entre utilizadores (alteração 7).
"""
from datetime import datetime
from pydantic import BaseModel, Field


class MessageCreate(BaseModel):
    body: str = Field(..., min_length=1, max_length=4000)


class MessageOut(BaseModel):
    id: int
    sender_id: int
    recipient_id: int
    body: str
    is_read: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationOut(BaseModel):
    """Uma linha da lista de conversas — o correspondente + a última mensagem."""
    user_id: int
    full_name: str
    role: str
    last_message: str
    last_message_at: datetime
    unread_count: int


class UnreadCountOut(BaseModel):
    unread: int


class ColleagueOut(BaseModel):
    """Um colega da mesma empresa disponível para iniciar conversa."""
    id: int
    full_name: str
    role: str
