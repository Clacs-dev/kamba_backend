"""
Schemas Pydantic — dossier (documentos e assinaturas).
"""
from datetime import datetime
from pydantic import BaseModel, Field

from app.models.enums import DocumentType, SignatureType


class DocumentCreate(BaseModel):
    title: str = Field(..., min_length=2, max_length=200)
    doc_type: DocumentType = DocumentType.OUTRO
    content: str = Field(..., min_length=1)


class DocumentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    doc_type: DocumentType | None = None
    content: str | None = Field(default=None, min_length=1)
    is_active: bool | None = None


class DocumentSummary(BaseModel):
    id: int
    title: str
    doc_type: DocumentType
    is_active: bool
    created_at: datetime
    model_config = {"from_attributes": True}


class DocumentDetail(BaseModel):
    id: int
    company_id: int
    title: str
    doc_type: DocumentType
    content: str
    is_active: bool
    created_at: datetime
    model_config = {"from_attributes": True}


class DocumentReadReceipt(BaseModel):
    document_id: int
    user_id: int
    read_at: datetime
    model_config = {"from_attributes": True}


class SignatureCreate(BaseModel):
    signature_type: SignatureType


class SignatureOut(BaseModel):
    id: int
    user_id: int
    signature_type: SignatureType
    signed_at: datetime
    model_config = {"from_attributes": True}