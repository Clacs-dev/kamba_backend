"""
Rotas de turnos (alterações 8 e 9).

Só faz sentido usar turnos quando `Company.uses_shifts` está activo — esse
toggle vive em `admin.py` (`PUT /admin/company/shifts`), junto ao resto da
configuração da empresa. Aqui fica só o CRUD do catálogo de turnos.

Isolamento multi-tenant: todos os turnos pertencem à empresa do utilizador
autenticado — mesma regra de ouro do resto do projecto.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.models.enums import UserRole
from app.models.shift import Shift
from app.schemas.shift import ShiftCreate, ShiftUpdate, ShiftOut
from app.api.deps import require_roles

router = APIRouter(prefix="/companies/shifts", tags=["shifts"])

# Mesmo grupo de perfis que gere colaboradores/administração (collaborators.py, admin.py).
MANAGE_ROLES = (UserRole.CAPITAL_HUMANO, UserRole.ADMINISTRACAO, UserRole.ADMIN)


def _get_company_shift_or_404(db: Session, company_id: int, shift_id: int) -> Shift:
    shift = (
        db.query(Shift)
        .filter(Shift.id == shift_id, Shift.company_id == company_id)
        .first()
    )
    if shift is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Turno não encontrado.")
    return shift


@router.get("", response_model=list[ShiftOut])
def list_shifts(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    """Lista os turnos da empresa (activos e inactivos)."""
    return (
        db.query(Shift)
        .filter(Shift.company_id == current_user.company_id)
        .order_by(Shift.name)
        .all()
    )


@router.post("", response_model=ShiftOut, status_code=status.HTTP_201_CREATED)
def create_shift(
    payload: ShiftCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    """Cria um turno na empresa do utilizador autenticado."""
    shift = Shift(company_id=current_user.company_id, **payload.model_dump())
    db.add(shift)
    db.commit()
    db.refresh(shift)
    return shift


@router.patch("/{shift_id}", response_model=ShiftOut)
def update_shift(
    shift_id: int,
    payload: ShiftUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    """Actualiza um turno da empresa."""
    shift = _get_company_shift_or_404(db, current_user.company_id, shift_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(shift, field, value)
    db.commit()
    db.refresh(shift)
    return shift


@router.delete("/{shift_id}")
def deactivate_shift(
    shift_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    """
    Desactiva um turno (não apaga — colaboradores já associados mantêm a
    referência histórica; deixa apenas de aparecer como opção nova).
    """
    shift = _get_company_shift_or_404(db, current_user.company_id, shift_id)
    shift.is_active = False
    db.commit()
    return {"detail": "Turno desactivado."}
