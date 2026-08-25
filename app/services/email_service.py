"""
Serviço de envio de emails via SMTP (Gmail) — email centralizado da plataforma.
Credenciais em variáveis de ambiente (.env / Render):
  SMTP_HOST (por omissão smtp.gmail.com), SMTP_PORT (587),
  SMTP_USER (email remetente), SMTP_PASSWORD (app password de 16 letras),
  SMTP_FROM_NAME (nome do remetente, por omissão "KAMBA").
Se não estiver configurado, o envio é ignorado sem falhar (devolve False).
"""
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from dotenv import load_dotenv
load_dotenv()


def _config():
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    from_name = os.getenv("SMTP_FROM_NAME", "KAMBA")
    return host, port, user, password, from_name


def enviar_email(destinatario: str, assunto: str, corpo_html: str) -> bool:
    host, port, user, password, from_name = _config()
    if not (user and password):
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = assunto
        msg["From"] = f"{from_name} <{user}>"
        msg["To"] = destinatario
        msg.attach(MIMEText(corpo_html, "html", "utf-8"))
        with smtplib.SMTP(host, port, timeout=15) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(user, [destinatario], msg.as_string())
        return True
    except Exception as e:
        print(f"[EMAIL] Falha ao enviar para {destinatario}: {e}")
        return False


def email_boas_vindas(nome: str, email: str, senha_temporaria: str, empresa: str = "") -> bool:
    empresa_txt = f" da {empresa}" if empresa else ""
    corpo = f"""
    <div style="font-family: Arial, sans-serif; max-width: 520px; margin: 0 auto; color: #1a1a1a;">
      <div style="background: #1a5f4a; padding: 20px; border-radius: 8px 8px 0 0;">
        <h1 style="color: #fff; margin: 0; font-size: 22px;">KAMBA</h1>
      </div>
      <div style="border: 1px solid #e0e0e0; border-top: none; padding: 24px; border-radius: 0 0 8px 8px;">
        <p>Caro(a) <b>{nome}</b>,</p>
        <p>A sua conta encontra-se ativa na plataforma KAMBA{empresa_txt}.
           Utilize o seu email e a senha temporária abaixo para fazer login.</p>
        <div style="background: #f5f5f5; border-radius: 8px; padding: 16px; margin: 18px 0;">
          <p style="margin: 0 0 8px;"><b>Email:</b> {email}</p>
          <p style="margin: 0;"><b>Senha temporária:</b>
             <span style="font-family: monospace; font-size: 16px; color: #1a5f4a;">{senha_temporaria}</span></p>
        </div>
        <p style="font-size: 13px; color: #666;">
          Por segurança, ser-lhe-á pedido para alterar esta senha no primeiro acesso.</p>
        <p style="font-size: 13px; color: #666;">Cumprimentos,<br>Equipa KAMBA</p>
      </div>
    </div>
    """
    return enviar_email(email, "A sua conta KAMBA está ativa", corpo)