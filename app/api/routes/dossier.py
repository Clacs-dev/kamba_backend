"""
Rotas do dossier: documentos (2.4) e assinaturas (2.2).
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.models.enums import UserRole
from app.models.dossier import Document, DocumentRead, Signature
from app.schemas.dossier import (
    DocumentCreate, DocumentUpdate, DocumentSummary, DocumentDetail,
    DocumentReadReceipt, SignatureCreate, SignatureOut,
)
from app.api.deps import get_current_user, require_roles

router = APIRouter(tags=["dossier"])

MANAGE_ROLES = (UserRole.CAPITAL_HUMANO, UserRole.ADMINISTRACAO)


@router.post("/documents", response_model=DocumentDetail, status_code=status.HTTP_201_CREATED)
def create_document(
    payload: DocumentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    doc = Document(
        company_id=current_user.company_id,
        title=payload.title,
        doc_type=payload.doc_type,
        content=payload.content,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


@router.patch("/documents/{document_id}", response_model=DocumentDetail)
def update_document(
    document_id: int,
    payload: DocumentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    doc = (
        db.query(Document)
        .filter(Document.id == document_id, Document.company_id == current_user.company_id)
        .first()
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(doc, field, value)
    db.commit()
    db.refresh(doc)
    return doc


@router.get("/documents", response_model=list[DocumentSummary])
def list_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(Document)
        .filter(Document.company_id == current_user.company_id, Document.is_active == True)  # noqa: E712
        .order_by(Document.title)
        .all()
    )


@router.get("/documents/{document_id}", response_model=DocumentDetail)
def read_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = (
        db.query(Document)
        .filter(Document.id == document_id, Document.company_id == current_user.company_id)
        .first()
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")

    existing = (
        db.query(DocumentRead)
        .filter(DocumentRead.document_id == doc.id, DocumentRead.user_id == current_user.id)
        .first()
    )
    if existing is None:
        db.add(DocumentRead(
            company_id=current_user.company_id,
            document_id=doc.id,
            user_id=current_user.id,
        ))
        db.commit()

    return doc


@router.get("/documents/{document_id}/reads", response_model=list[DocumentReadReceipt])
def list_document_reads(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    doc = (
        db.query(Document)
        .filter(Document.id == document_id, Document.company_id == current_user.company_id)
        .first()
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    return (
        db.query(DocumentRead)
        .filter(DocumentRead.document_id == doc.id)
        .order_by(DocumentRead.read_at)
        .all()
    )


@router.post("/me/signatures", response_model=SignatureOut, status_code=status.HTTP_201_CREATED)
def sign(
    payload: SignatureCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing = (
        db.query(Signature)
        .filter(
            Signature.user_id == current_user.id,
            Signature.signature_type == payload.signature_type,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Esta assinatura já foi registada.")

    sig = Signature(
        company_id=current_user.company_id,
        user_id=current_user.id,
        signature_type=payload.signature_type,
    )
    db.add(sig)
    db.commit()
    db.refresh(sig)
    return sig


@router.get("/me/signatures", response_model=list[SignatureOut])
def my_signatures(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(Signature)
        .filter(Signature.user_id == current_user.id)
        .order_by(Signature.signed_at)
        .all()
    )