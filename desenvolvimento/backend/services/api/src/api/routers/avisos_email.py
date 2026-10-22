"""Inscricao nos avisos por e-mail (CDU06, canal alternativo ao push), com confirmacao por link."""

import re
from datetime import datetime, timedelta
from typing import Annotated

from common.models import Estacao, InscricaoEmail
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from api import avisos_email
from api.deps import obter_agora, obter_sessao
from api.limite import LimiteTaxa, exigir, ip_do_cliente
from api.push import FAIXAS_VALIDAS
from api.schemas import InscricaoEmailIn, MensagemOut, TokenIn

router = APIRouter(prefix="/inscricoes/email", tags=["avisos"])
limite_email = LimiteTaxa(5, timedelta(hours=1))
VALIDADE_CONFIRMACAO = timedelta(hours=48)
FORMATO_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

SessaoDep = Annotated[Session, Depends(obter_sessao)]
AgoraDep = Annotated[datetime, Depends(obter_agora)]


def obter_enviador() -> avisos_email.EnviadorEmail:
    return avisos_email.EnviadorSMTP()


EnviadorDep = Annotated[avisos_email.EnviadorEmail, Depends(obter_enviador)]


@router.post("", response_model=MensagemOut, status_code=202)
def inscrever(
    dados: InscricaoEmailIn, req: Request, s: SessaoDep, agora: AgoraDep, enviador: EnviadorDep
) -> MensagemOut:
    """Envia o link de confirmacao. A resposta e a mesma exista ou nao o e-mail (nao revela)."""
    exigir(limite_email, ip_do_cliente(req), agora)
    email = dados.email.strip().lower()
    if not FORMATO_EMAIL.match(email):
        raise HTTPException(422, "Confira o e-mail digitado.")
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

    token, token_hash = avisos_email.novo_token()
    i = s.scalar(select(InscricaoEmail).where(InscricaoEmail.email == email))
    if i is None:
        i = InscricaoEmail(email=email, faixa_minima=dados.faixa_minima, estacao_id=estacao_id)
        s.add(i)
    # preferencias novas so valem depois de confirmar de novo pelo link
    i.token_hash, i.criada_em, i.confirmada_em = token_hash, agora, None
    i.estacao_id, i.faixa_minima = estacao_id, dados.faixa_minima
    s.flush()
    assunto, texto = avisos_email.mensagem_confirmacao(token)
    r = enviador.enviar(email, assunto, texto)
    if not r.ok:
        raise HTTPException(503, "Não conseguimos enviar o e-mail agora. Tente de novo mais tarde.")
    return MensagemOut(
        status="pendente",
        mensagem="Enviamos um link para o seu e-mail. Abra o link para confirmar os avisos.",
    )


@router.post("/confirmar", response_model=MensagemOut)
def confirmar(dados: TokenIn, s: SessaoDep, agora: AgoraDep, enviador: EnviadorDep) -> MensagemOut:
    i = s.scalar(
        select(InscricaoEmail).where(
            InscricaoEmail.token_hash == avisos_email.hash_token(dados.token)
        )
    )
    if i is None or (i.confirmada_em is None and agora - i.criada_em > VALIDADE_CONFIRMACAO):
        raise HTTPException(404, "Link inválido ou vencido. Peça os avisos de novo.")
    if i.confirmada_em is None:
        i.confirmada_em = agora
        s.flush()
        assunto, texto = avisos_email.mensagem_ativado(i)
        enviador.enviar(i.email, assunto, texto)  # boas-vindas: falha aqui nao desfaz
    return MensagemOut(status="confirmado", mensagem="Pronto! Os avisos por e-mail estão ativos.")


@router.post("/cancelar", response_model=MensagemOut)
def cancelar(dados: TokenIn, s: SessaoDep) -> MensagemOut:
    """Apaga o e-mail e o historico de envios (LGPD). Link de cancelar de qualquer aviso."""
    i = avisos_email.inscricao_do_token_cancelar(s, dados.token)
    if i is None:
        raise HTTPException(404, "Link inválido.")
    s.execute(delete(InscricaoEmail).where(InscricaoEmail.id == i.id))
    s.flush()
    return MensagemOut(status="cancelado", mensagem="Pronto. Você não vai mais receber avisos.")
