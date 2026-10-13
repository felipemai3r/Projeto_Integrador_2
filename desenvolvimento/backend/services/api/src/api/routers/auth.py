from datetime import UTC, datetime, timedelta
from typing import Annotated

from common.models import Usuario
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import obter_agora, obter_sessao
from api.limite import LimiteTaxa, exigir, ip_do_cliente
from api.schemas import LoginIn, TokenOut
from api.seguranca import criar_token, verificar_senha

router = APIRouter(prefix="/auth", tags=["acesso"])
limite_login = LimiteTaxa(10, timedelta(minutes=15))
_SENHA_FALSA = (
    "scrypt$16384$8$1$AAAAAAAAAAAAAAAAAAAAAA==$AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
)


@router.post("/login", response_model=TokenOut)
def login(
    dados: LoginIn,
    req: Request,
    s: Annotated[Session, Depends(obter_sessao)],
    agora: Annotated[datetime, Depends(obter_agora)],
) -> TokenOut:
    exigir(limite_login, ip_do_cliente(req), agora)
    u = s.scalar(select(Usuario).where(Usuario.email == dados.email.strip().lower(), Usuario.ativo))
    # a verificacao roda mesmo sem usuario, para o tempo de resposta nao revelar se o e-mail existe
    ok = verificar_senha(dados.senha, u.senha_hash if u else _SENHA_FALSA)
    if u is None or not ok:
        raise HTTPException(401, "E-mail ou senha incorretos.")
    token, expira = criar_token(u, datetime.now(UTC))
    return TokenOut(token=token, nome=u.nome, papel=u.papel, expira_em=expira)
