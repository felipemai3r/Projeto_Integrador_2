"""Tratamento de foto de ocorrencia (RF23, LGPD).

Remove todos os metadados (EXIF inclui GPS e modelo do aparelho), corrige a rotacao,
reduz para no maximo 1280 px e regrava em JPEG. O nome do arquivo e gerado pelo servidor.
"""

import io
import uuid
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

TIPOS_ACEITOS = {"image/jpeg", "image/png", "image/webp"}
TAMANHO_MAX = 5 * 1024 * 1024
LADO_MAX = 1280


class FotoInvalida(ValueError):
    pass


def tratar_e_salvar(conteudo: bytes, content_type: str | None, pasta: str) -> str:
    """Devolve o nome do arquivo salvo. Levanta FotoInvalida com mensagem para o usuario."""
    if content_type not in TIPOS_ACEITOS:
        raise FotoInvalida("Envie uma foto em JPEG, PNG ou WebP.")
    if len(conteudo) > TAMANHO_MAX:
        raise FotoInvalida("A foto tem mais de 5 MB. Envie uma menor.")
    try:
        with Image.open(io.BytesIO(conteudo)) as img:
            img.verify()
        with Image.open(io.BytesIO(conteudo)) as img:
            img = ImageOps.exif_transpose(img).convert("RGB")
            img.thumbnail((LADO_MAX, LADO_MAX))
            limpa = Image.new("RGB", img.size)
            limpa.paste(img)  # copia so os pixels: nenhum metadado acompanha
            Path(pasta).mkdir(parents=True, exist_ok=True)
            nome = f"{uuid.uuid4().hex}.jpg"
            limpa.save(Path(pasta) / nome, "JPEG", quality=80, optimize=True)
            return nome
    except (UnidentifiedImageError, OSError, SyntaxError) as e:
        raise FotoInvalida("Não conseguimos ler essa foto. Tente outra.") from e
