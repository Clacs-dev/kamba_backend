"""
Rotas dos Órgãos Sociais da empresa.

O Capital Humano / Administração / Admin gere os membros de cada órgão
(Conselho de Administração, Comissão Executiva, Conselho Fiscal, Mesa da
Assembleia), atribuindo-lhes o cargo dentro do órgão (ex.: Presidente,
Vice-presidente, Vogal). Isolamento por company_id.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.models.enums import UserRole, CompanyOrgan
from app.models.organ import OrganMember
from app.api.deps import get_current_user, require_roles
from app.services.audit import audit

router = APIRouter(prefix="/organs", tags=["organs"])

MANAGE_ROLES = (UserRole.CAPITAL_HUMANO, UserRole.ADMINISTRACAO, UserRole.ADMIN)

# Rótulos dos órgãos para resposta da API.
ORGAN_LABELS = {
    CompanyOrgan.CONSELHO_ADMINISTRACAO: "Conselho de Administração",
    CompanyOrgan.COMISSAO_EXECUTIVA: "Comissão Executiva",
    CompanyOrgan.CONSELHO_FISCAL: "Conselho Fiscal",
    CompanyOrgan.MESA_ASSEMBLEIA: "Mesa da Assembleia",
}


class OrganMemberIn(BaseModel):
    user_id: int
    organ: CompanyOrgan
    organ_role: str | None = Field(default=None, max_length=100)


@router.get("")
def list_organs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Membros de todos os órgãos da empresa, agrupados por órgão."""
    rows = (
        db.query(OrganMember, User)
        .join(User, User.id == OrganMember.user_id)
        .filter(OrganMember.company_id == current_user.company_id)
        .order_by(OrganMember.organ, User.full_name)
        .all()
    )

    agrupado: dict[str, list] = {}
    for membro, user in rows:
        key = membro.organ.value
        agrupado.setdefault(key, []).append(
            {
                "id": membro.id,
                "user_id": user.id,
                "full_name": user.full_name,
                "role": user.role.value if hasattr(user.role, "value") else str(user.role),
                "organ_role": membro.organ_role,
                "appointed_at": membro.appointed_at.isoformat() if membro.appointed_at else None,
            }
        )

    return [
        {
            "organ": o.value,
            "label": ORGAN_LABELS[o],
            "members": agrupado.get(o.value, []),
        }
        for o in CompanyOrgan
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
def add_organ_member(
    payload: OrganMemberIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    """Adiciona um colaborador a um órgão social (com cargo no órgão)."""
    user = (
        db.query(User)
        .filter(User.id == payload.user_id, User.company_id == current_user.company_id)
        .first()
    )
    if user is None:
        raise HTTPException(status_code=404, detail="Colaborador não encontrado nesta empresa.")

    existe = (
        db.query(OrganMember)
        .filter(
            OrganMember.company_id == current_user.company_id,
            OrganMember.organ == payload.organ,
            OrganMember.user_id == payload.user_id,
        )
        .first()
    )
    if existe:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este colaborador já pertence a este órgão social.",
        )

    membro = OrganMember(
        company_id=current_user.company_id,
        organ=payload.organ,
        user_id=payload.user_id,
        organ_role=payload.organ_role,
    )
    db.add(membro)
    audit(db, actor=current_user, action="organs.membro_adicionado",
          detail=f"{user.full_name} adicionado ao {ORGAN_LABELS[payload.organ]}"
                 + (f" ({payload.organ_role})" if payload.organ_role else "") + ".")
    db.commit()
    db.refresh(membro)
    return {
        "id": membro.id,
        "organ": membro.organ.value,
        "user_id": user.id,
        "full_name": user.full_name,
        "organ_role": membro.organ_role,
    }


@router.delete("/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_organ_member(
    member_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    """Remove um membro de um órgão social."""
    membro = (
        db.query(OrganMember)
        .filter(
            OrganMember.id == member_id,
            OrganMember.company_id == current_user.company_id,
        )
        .first()
    )
    if membro is None:
        raise HTTPException(status_code=404, detail="Membro não encontrado.")

    user = db.query(User).filter(User.id == membro.user_id).first()
    nome = user.full_name if user else f"#{membro.user_id}"
    db.delete(membro)
    audit(db, actor=current_user, action="organs.membro_removido",
          detail=f"{nome} removido do {ORGAN_LABELS[membro.organ]}.")
    db.commit()