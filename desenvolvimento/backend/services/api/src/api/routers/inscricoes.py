from datetime import timedelta
from typing import Annotated
from urllib.parse import urlparse

from common.config import obter_configuracao
from common.models import Estacao, Inscricao, Notificacao
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from api.deps import obter_agora, obter_sessao
from api.limite import LimiteTaxa, exigir, ip_do_cliente
from api.push import FAIXAS_VALIDAS
from api.schemas import CancelamentoIn, ChavePublica, InscricaoIn

router = APIRouter(tags=["avisos"])
limite_inscricao = LimiteTaxa(20, timedelta(hours=1))

# O servidor envia para o endpoint informado pelo usuario. Aceitar qualquer URL abriria o servidor
# para requisicoes a enderecos arbitrarios (SSRF). So os servicos de push dos navegadores passam.
SUFIXOS_PERMITIDOS = (
    ".googleapis.com",
    ".push.services.mozilla.com",
    ".notify.windows.com",
    ".push.apple.com",
)


def endpoint_permitido(url: str) -> bool:
    p = urlparse(url)
    host = (p.hostname or "").lower()
    return (
        p.scheme == "https"
        and len(url) <= 2048
        and p.port in (None, 443)
        and any(host.endswith(s) for s in SUFIXOS_PERMITIDOS)
    )


@router.get("/push/chave", response_model=ChavePublica)
def chave_publica() -> ChavePublica:
    cfg = obter_configuracao()
    return ChavePublica(configurado=bool(cfg.vapid_public_key), chave_publica=cfg.vapid_public_key)


@router.post("/inscricoes", status_code=201)
def inscrever(
    dados: InscricaoIn,
    req: Request,
    s: Annotated[Session, Depends(obter_sessao)],
    agora: Annotated[object, Depends(obter_agora)],
) -> dict[str, str]:
    """Inscricao de push, sem login (CDU06). Chamar de novo atualiza as preferencias."""
    exigir(limite_inscricao, ip_do_cliente(req), agora)  # type: ignore[arg-type]
    if not endpoint_permitido(dados.endpoint):
        raise HTTPException(422, "Este aparelho ou navegador não é compatível com os avisos.")
    if dados.faixa_minima not in FAIXAS_VALIDAS:
        raise HTTPException(422, "Escolha a partir de qual faixa quer ser avisado.")
    estacao_id = None
    if dados.estacao:
        est = s.scalar(
            select(Estacao).where(Estacao.codigo == dados.estacao, Estacao.papel == "alvo")
        )
        if est is None:
            raise HTTPException(422, "Estação inválida.")
        estacao_id = est.id
    i = s.scalar(select(Inscricao).where(Inscricao.endpoint == dados.endpoint))
    if i is None:
        i = Inscricao(
            endpoint=dados.endpoint,
            chave_p256dh=dados.keys.p256dh,
            chave_auth=dados.keys.auth,
            estacao_id=estacao_id,
            faixa_minima=dados.faixa_minima,
        )
        s.add(i)
    else:
        i.chave_p256dh, i.chave_auth = dados.keys.p256dh, dados.keys.auth
        i.estacao_id, i.faixa_minima, i.ativa = estacao_id, dados.faixa_minima, True
    s.flush()
    return {"status": "inscrito"}


@router.delete("/inscricoes")
def cancelar(dados: CancelamentoIn, s: Annotated[Session, Depends(obter_sessao)]) -> dict[str, str]:
    """Remove a inscricao e o historico de envios dela (RF39, LGPD). Idempotente."""
    i = s.scalar(select(Inscricao).where(Inscricao.endpoint == dados.endpoint))
    if i is not None:
        s.execute(delete(Notificacao).where(Notificacao.inscricao_id == i.id))
        s.delete(i)
        s.flush()
    return {"status": "cancelado"}
