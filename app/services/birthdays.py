"""
Serviço de aniversários — envia parabéns aos aniversariantes.

A cada execução (arranque e depois periodicamente), para cada colaborador com
data de nascimento cujo dia/mês coincidem com hoje:
  * envia um email de feliz aniversário ao próprio;
  * notifica todos os colaboradores ativos da empresa ("X faz anos hoje!").

Guarda `birthday_notified_year` na ficha para não repetir o mesmo parabéns
duas vezes no mesmo ano (idempotente).
"""
from datetime import date

from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.models.user import User
from app.models.employee_profile import EmployeeProfile
from app.services.email_service import enviar_email
from app.services.notifications import notify


def processar_aniversarios(db: Session) -> tuple[int, int]:
    """
    Devolve (emails_enviados, notificacoes_criadas). Não falha se o email não
    estiver configurado — a notificação interna continua a ser criada.
    """
    hoje = date.today()
    aniversariantes = (
        db.query(User, EmployeeProfile)
        .join(EmployeeProfile, EmployeeProfile.user_id == User.id)
        .filter(
            EmployeeProfile.birth_date.isnot(None),
            or_(
                EmployeeProfile.birthday_notified_year.is_(None),
                EmployeeProfile.birthday_notified_year != hoje.year,
            ),
        )
        .all()
    )

    emails = 0
    nots = 0
    for user, perfil in aniversariantes:
        if perfil.birth_date is None:
            continue
        if perfil.birth_date.month != hoje.month or perfil.birth_date.day != hoje.day:
            continue

        nome = user.full_name.split()[0] if user.full_name else "Caríssimo(a)"
        enviar_email(
            user.email,
            "Feliz Aniversário 🎂",
            f"""
            <div style="font-family: Arial, sans-serif; max-width: 520px; margin: 0 auto; color: #1a1a1a;">
              <div style="background: #1a5f4a; padding: 20px; border-radius: 8px 8px 0 0;">
                <h1 style="color: #fff; margin: 0; font-size: 22px;">Feliz Aniversário 🎂</h1>
              </div>
              <div style="border: 1px solid #e0e0e0; border-top: none; padding: 24px; border-radius: 0 0 8px 8px;">
                <p>Caro(a) <b>{nome}</b>,</p>
                <p style="font-size: 15px;">A equipa KAMBA deseja-lhe um dia muito feliz, cheio de
                   saúde, sucesso e boas energias.</p>
                <p style="font-size: 13px; color: #666;">Cumprimentos,<br>Equipa KAMBA</p>
              </div>
            </div>
            """,
        )
        emails += 1

        colegas = (
            db.query(User)
            .filter(
                User.company_id == user.company_id,
                User.is_active == True,  # noqa: E712
                User.id != user.id,
            )
            .all()
        )
        for colega in colegas:
            notify(
                db,
                company_id=user.company_id,
                user_id=colega.id,
                title="🎂 Aniversário",
                message=f"{user.full_name} faz anos hoje. Envie os parabéns!",
                category="aniversario",
                link="/colaboradores",
            )
            nots += 1

        perfil.birthday_notified_year = hoje.year

    if aniversariantes:
        db.commit()
    return emails, nots