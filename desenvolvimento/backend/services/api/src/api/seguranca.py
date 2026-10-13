"""Senhas, tokens e controle de acesso de quem modera. O cidadao nao tem conta (RF22, RN06).

- Senha: scrypt (biblioteca padrao), sal aleatorio por usuario, comparacao em tempo constante.
- Token: JWT HS256 de curta duracao, com o papel. O segredo vem do ambiente (RNF09).
"""

import base64
import hashlib
import hmac
import os
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from common.config import obter_configuracao
from common.models import Usuario
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import obter_sessao

_N, _R, _P = 2**14, 8, 1
PAPEIS = ("admin", "moderador")
_esquema = HTTPBearer(auto_error=False)


def hash_senha(senha: str) -> str:
    sal = os.urandom(16)
    h = hashlib.scrypt(senha.encode(), salt=sal, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${base64.b64encode(sal).decode()}${base64.b64encode(h).decode()}"


def verificar_senha(senha: str, armazenado: str) -> bool:
    try:
        _, n, r, p, sal, esperado = armazenado.split("$")
        h = hashlib.scrypt(
            senha.encode(), salt=base64.b64decode(sal), n=int(n), r=int(r), p=int(p), dklen=32
        )
        return hmac.compare_digest(h, base64.b64decode(esperado))
    except (ValueError, TypeError):
        return False


def criar_token(usuario: Usuario, agora: datetime | None = None) -> tuple[str, datetime]:
    cfg = obter_configuracao()
    expira = (agora or datetime.now(UTC)) + timedelta(hours=cfg.jwt_horas)
    token = jwt.encode(
        {"sub": usuario.email, "papel": usuario.papel, "exp": expira},
        cfg.jwt_secret,
        algorithm="HS256",
    )
    return token, expira


def usuario_opcional(
    cred: Annotated[HTTPAuthorizationCredentials | None, Depends(_esquema)],
    s: Annotated[Session, Depends(obter_sessao)],
) -> Usuario | None:
    """Usuario do token, ou None se nao enviou token. Token invalido ou expirado e 401."""
    if cred is None:
        return None
    try:
        dados = jwt.decode(cred.credentials, obter_configuracao().jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as e:
        raise HTTPException(401, "Sessão inválida ou expirada. Entre de novo.") from e
    u = s.scalar(select(Usuario).where(Usuario.email == dados.get("sub"), Usuario.ativo))
    if u is None:
        raise HTTPException(401, "Usuário não encontrado ou desativado.")
    return u


def exigir_moderador(u: Annotated[Usuario | None, Depends(usuario_opcional)]) -> Usuario:
    if u is None:
        raise HTTPException(401, "Entre para continuar.")
    if u.papel not in PAPEIS:
        raise HTTPException(403, "Sem permissão para esta ação.")
    return u
