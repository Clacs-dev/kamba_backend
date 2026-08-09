"""
Rotas da lista de verificação de acolhimento (secção 2.2).

- O Capital Humano cria itens, marca-os e vê a checklist de qualquer colaborador.
- O colaborador vê a sua própria checklist.
Isolamento por company_id.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.models.enums import UserRole
from app.models.onboarding import OnboardingItem
from app.api.deps import get_current_user, require_roles

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

MANAGE = (UserRole.CAPITAL_HUMANO, UserRole.ADMINISTRACAO)


class ItemIn(BaseModel):
    collaborator_id: int
    description: str = Field(..., min_length=2, max_length=200)


class ItemOut(BaseModel):
    id: int
    collaborator_id: int
    description: str
    done: bool
    model_config = {"from_attributes": True}


def _get_item(db, company_id, item_id) -> OnboardingItem:
    item = (
        db.query(OnboardingItem)
        .filter(OnboardingItem.id == item_id, OnboardingItem.company_id == company_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Item não encontrado.")
    return item


@router.get("/{collaborator_id}", response_model=list[ItemOut])
def list_items(
    collaborator_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista a checklist de um colaborador. O próprio vê a sua; a gestão vê todas."""
    if current_user.role not in MANAGE and current_user.id != collaborator_id:
        raise HTTPException(status_code=403, detail="Sem acesso.")
    return (
        db.query(OnboardingItem)
        .filter(
            OnboardingItem.company_id == current_user.company_id,
            OnboardingItem.collaborator_id == collaborator_id,
        )
        .order_by(OnboardingItem.id)
        .all()
    )


@router.post("", response_model=ItemOut, status_code=201)
def create_item(
    payload: ItemIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE)),
):
    """O Capital Humano acrescenta um item à checklist de um colaborador."""
    item = OnboardingItem(
        company_id=current_user.company_id,
        collaborator_id=payload.collaborator_id,
        description=payload.description,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.post("/{item_id}/toggle", response_model=ItemOut)
def toggle_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE)),
):
    """Marca/desmarca um item como concluído."""
    item = _get_item(db, current_user.company_id, item_id)
    item.done = not item.done
    db.commit()
    db.refresh(item)
    return item
