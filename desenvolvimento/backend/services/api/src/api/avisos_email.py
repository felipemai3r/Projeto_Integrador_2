"""Avisos por e-mail (CDU07, canal alternativo ao push).

- So recebe quem confirmou o e-mail pelo link (evita cadastrar o e-mail de outra pessoa, LGPD).
- Mesmas regras do push: RN02 (so a subida notifica; o encerramento avisa quem recebeu a
  abertura), RN03 (observado ou previsto) e RN09 (fonte oficial). O texto vem do push.
- Todo e-mail traz o link para cancelar. Falha de envio fica registrada e nunca desfaz o alerta.
"""

import hashlib
import hmac
import logging
import secrets
import smtplib
from email.message import EmailMessage
from typing import Protocol

from common.config import obter_configuracao
from common.enums import Faixa
from common.models import Alerta, Estacao, InscricaoEmail, NotificacaoEmail
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.alertas import ORDEM
from api.push import FAIXAS_VALIDAS, Resultado, montar_abertura, montar_encerramento

log = logging.getLogger("api.email")
RODAPE = (
    "\n\nEstimativa de apoio, não é um alerta oficial. "
    "A fonte oficial é a Defesa Civil de Presidente Getúlio (199).\n"
    "Para parar de receber estes avisos: {link}\n"
)


class EnviadorEmail(Protocol):
    def enviar(self, destino: str, assunto: str, texto: str) -> Resultado: ...


class EnviadorSMTP:
    """Envio real via SMTP. Sem SMTP_HOST configurado, nao envia (e registra)."""

    def enviar(self, destino: str, assunto: str, texto: str) -> Resultado:
        cfg = obter_configuracao()
        if not cfg.smtp_host:
            return Resultado(False, erro="SMTP nao configurado")
        msg = EmailMessage()
        msg["From"] = cfg.email_remetente
        msg["To"] = destino
        msg["Subject"] = assunto
        msg.set_content(texto)
        try:
            with smtplib.SMTP(cfg.smtp_host, cfg.smtp_porta, timeout=15) as smtp:
                if cfg.smtp_starttls:
                    smtp.starttls()
                if cfg.smtp_usuario:
                    smtp.login(cfg.smtp_usuario, cfg.smtp_senha)
                smtp.send_message(msg)
            return Resultado(True)
        except Exception as e:  # rede, autenticacao, recusa do servidor
            return Resultado(False, erro=f"{type(e).__name__}: {e}"[:300])


def novo_token() -> tuple[str, str]:
    """Token do link de confirmacao (vai so no e-mail) e o hash dele (vai para o banco)."""
    token = secrets.token_urlsafe(32)
    return token, hash_token(token)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _assinatura(i: InscricaoEmail) -> str:
    chave = obter_configuracao().jwt_secret.encode()
    return hmac.new(chave, f"cancelar:{i.id}:{i.email}".encode(), hashlib.sha256).hexdigest()[:32]


def token_cancelar(i: InscricaoEmail) -> str:
    """Estavel e assinado: o link de qualquer e-mail ja enviado continua valido."""
    return f"{i.id}.{_assinatura(i)}"


def inscricao_do_token_cancelar(s: Session, token: str) -> InscricaoEmail | None:
    id_, _, assinatura = token.partition(".")
    if not id_.isdigit():
        return None
    i = s.get(InscricaoEmail, int(id_))
    if i is None or not hmac.compare_digest(assinatura, _assinatura(i)):
        return None
    return i


def link(acao: str, token: str) -> str:
    """Os links abrem a pagina Avisos, que confirma ou cancela com um POST. Um GET direto na
    API deixaria filtros de e-mail (que abrem links sozinhos) confirmar ou cancelar por engano."""
    return f"{obter_configuracao().url_publica}/avisos?{acao}={token}"


def mensagem_confirmacao(token: str, ja_ativa: bool = False) -> tuple[str, str]:
    if ja_ativa:
        # vai para o dono do e-mail: pode dizer que ja recebe, sem expor nada a quem pediu
        return (
            "Confirme a mudança nos avisos do nível do rio",
            "Alguém pediu para mudar os avisos de cheia que este e-mail recebe de Presidente "
            "Getúlio.\n\n"
            f"Para aplicar a mudança, abra: {link('confirmar', token)}\n\n"
            "Se não foi você, ignore esta mensagem: seus avisos continuam como estão.",
        )
    return (
        "Confirme os avisos do nível do rio",
        "Alguém pediu para receber neste e-mail os avisos de cheia dos rios de Presidente "
        "Getúlio.\n\n"
        f"Para confirmar, abra: {link('confirmar', token)}\n\n"
        "Se não foi você, ignore esta mensagem: sem confirmar, nada é enviado e o pedido "
        "é apagado.",
    )


def mensagem_ativado(i: InscricaoEmail) -> tuple[str, str]:
    return (
        "Avisos por e-mail ativados",
        "Pronto. Você vai receber um e-mail quando o nível do rio subir para a faixa que "
        "escolheu, e outro quando voltar ao normal."
        + RODAPE.format(link=link("cancelar", token_cancelar(i))),
    )


def _elegiveis(s: Session, estacao: Estacao, faixa: Faixa) -> list[InscricaoEmail]:
    minimo = ORDEM[faixa]
    return [
        i
        for i in s.scalars(
            select(InscricaoEmail).where(
                InscricaoEmail.confirmada_em.is_not(None),
                (InscricaoEmail.estacao_id.is_(None)) | (InscricaoEmail.estacao_id == estacao.id),
            )
        )
        if i.faixa_minima in FAIXAS_VALIDAS and ORDEM[Faixa(i.faixa_minima)] <= minimo
    ]


def _enviar(
    s: Session,
    alerta_id: int,
    i: InscricaoEmail,
    tipo: str,
    payload: dict[str, str],
    enviador: EnviadorEmail,
) -> bool:
    texto = payload["corpo"] + RODAPE.format(link=link("cancelar", token_cancelar(i)))
    r = enviador.enviar(i.email, payload["titulo"], texto)
    s.add(
        NotificacaoEmail(
            alerta_id=alerta_id,
            inscricao_email_id=i.id,
            tipo=tipo,
            status="enviada" if r.ok else "falha",
            erro=r.erro,
        )
    )
    if not r.ok:
        log.warning("e-mail falhou", extra={"extra_campos": {"inscricao": i.id, "erro": r.erro}})
    return r.ok


def notificar_abertura(
    s: Session,
    est: Estacao,
    alerta: Alerta,
    enviador: EnviadorEmail,
    nivel_m: float | None = None,
    tendencia: str | None = None,
) -> int:
    payload = montar_abertura(est, alerta, nivel_m, tendencia)
    enviados = sum(
        _enviar(s, alerta.id, i, "abertura", payload, enviador)
        for i in _elegiveis(s, est, Faixa(alerta.faixa_nova))
    )
    s.flush()
    return enviados


def notificar_encerramento(
    s: Session,
    est: Estacao,
    alerta_encerrado: Alerta,
    enviador: EnviadorEmail,
    nivel_m: float | None = None,
) -> int:
    """Avisa so quem recebeu a abertura de algum alerta deste episodio."""
    ids_do_episodio = [
        a.id
        for a in s.scalars(
            select(Alerta)
            .where(Alerta.estacao_id == est.id, Alerta.criado_em <= alerta_encerrado.criado_em)
            .order_by(Alerta.criado_em.desc())
            .limit(10)
        )
    ]
    alvos = s.scalars(
        select(InscricaoEmail)
        .join(NotificacaoEmail, NotificacaoEmail.inscricao_email_id == InscricaoEmail.id)
        .where(
            InscricaoEmail.confirmada_em.is_not(None),
            NotificacaoEmail.alerta_id.in_(ids_do_episodio),
            NotificacaoEmail.tipo == "abertura",
            NotificacaoEmail.status == "enviada",
        )
        .distinct()
    ).all()
    payload = montar_encerramento(est, nivel_m)
    enviados = sum(
        _enviar(s, alerta_encerrado.id, i, "encerramento", payload, enviador) for i in alvos
    )
    s.flush()
    return enviados
