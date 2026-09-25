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
    try:
        import cloudinary
    except ImportError:
        print("[CLOUDINARY] Pacote 'cloudinary' não instalado — upload ignorado.")
        return False
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


def fetch_image(url: str, max_bytes: int = 5 * 1024 * 1024) -> Optional[bytes]:
    """
    Descarrega uma imagem já guardada no Cloudinary e devolve os bytes.

    Só aceita HTTPS no host de entrega do Cloudinary e limita o tamanho, para
    que a geração de PDF não dependa de um URL arbitrário guardado na base de
    dados. Devolve None em qualquer falha (o PDF é gerado sem imagem).
    """
    from urllib.parse import urlparse
    from urllib.request import Request, urlopen

    if not url:
        return None
    try:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "res.cloudinary.com":
            return None
        request = Request(url, headers={"User-Agent": "KAMBA-PDF/1.0"})
        with urlopen(request, timeout=10) as resposta:
            dados = resposta.read(max_bytes + 1)
        if not dados or len(dados) > max_bytes:
            return None
        return dados
    except Exception as e:
        print(f"[CLOUDINARY] Falha ao ler a imagem: {e}")
        return None
