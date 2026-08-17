"""
Serviço de upload de ficheiros para o Cloudinary.

As credenciais vêm de variáveis de ambiente (definidas no Render):
  CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET
Se não estiverem configuradas, o upload é ignorado graciosamente (devolve None
para o URL) — o pedido é criado na mesma, só sem o ficheiro guardado.
"""
import os
from typing import Optional
from dotenv import load_dotenv
load_dotenv()
_configured = False


def _ensure_config() -> bool:
    """Configura o Cloudinary a partir das variáveis de ambiente (uma vez)."""
    global _configured
    if _configured:
        return True
    cloud = os.getenv("CLOUDINARY_CLOUD_NAME")
    key = os.getenv("CLOUDINARY_API_KEY")
    secret = os.getenv("CLOUDINARY_API_SECRET")
    if not (cloud and key and secret):
        return False
    import cloudinary
    cloudinary.config(cloud_name=cloud, api_key=key, api_secret=secret, secure=True)
    _configured = True
    return True


def upload_file(file_bytes: bytes, filename: str, folder: str = "kamba") -> Optional[str]:
    """
    Envia um ficheiro (em bytes) para o Cloudinary e devolve o URL seguro.
    Se o Cloudinary não estiver configurado, devolve None sem falhar.
    """
    if not _ensure_config():
        return None
    try:
        import cloudinary.uploader
        result = cloudinary.uploader.upload(
            file_bytes,
            folder=folder,
            resource_type="auto",  # aceita PDF, imagem, etc.
            use_filename=True,
            unique_filename=True,
        )
        return result.get("secure_url")
    except Exception as e:
        # Não deixamos uma falha de upload impedir a criação do pedido.
        print(f"[CLOUDINARY] Falha no upload: {e}")
        return None
