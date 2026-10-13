"""Envio de notificacao push (Web Push com VAPID) quando o risco muda (CDU07).

- Elegivel: inscricao ativa cuja estacao (ou "todas") e cuja faixa minima correspondem ao alerta.
- RN02: so a transicao para faixa mais grave notifica; o encerramento avisa quem recebeu a abertura.
- RN03: o texto diz se e observado ou previsto. RN09: todo texto lembra a fonte oficial.
- 404 ou 410 do servico de push significa que a pessoa desinstalou ou revogou: a inscricao e
  desativada. Falha temporaria tem uma nova tentativa; o resultado de cada envio fica registrado.
"""

import json
import logging
import time
from dataclasses import dataclass
from typing import Protocol

from common.config import obter_configuracao
from common.enums import Faixa
from common.models import Alerta, Estacao, Inscricao, Notificacao
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.alertas import ORDEM

log = logging.getLogger("api.push")
ROTULOS = {"normal": "normal", "observacao": "observação", "atencao": "atenção", "alerta": "alerta"}
FAIXAS_VALIDAS = ("observacao", "atencao", "alerta")


@dataclass(frozen=True)
class Resultado:
    ok: bool
    expirada: bool = False
    erro: str | None = None


class Enviador(Protocol):
    def enviar(self, inscricao: Inscricao, payload: dict[str, str]) -> Resultado: ...


class EnviadorWebPush:
    """Envio real via pywebpush. Sem chaves VAPID configuradas, nao envia (e registra)."""

    def enviar(self, inscricao: Inscricao, payload: dict[str, str]) -> Resultado:
        from pywebpush import WebPushException, webpush

        cfg = obter_configuracao()
        if not cfg.vapid_private_key:
            return Resultado(False, erro="VAPID nao configurado")
        info = {
            "endpoint": inscricao.endpoint,
            "keys": {"p256dh": inscricao.chave_p256dh, "auth": inscricao.chave_auth},
        }
        for tentativa in (1, 2):
            try:
                webpush(
                    subscription_info=info,
                    data=json.dumps(payload, ensure_ascii=False),
                    vapid_private_key=cfg.vapid_private_key,
                    vapid_claims={"sub": cfg.vapid_subject},
                    ttl=3600,
                )
                return Resultado(True)
            except WebPushException as e:
                status = e.response.status_code if e.response is not None else None
                if status in (404, 410):
                    return Resultado(False, expirada=True, erro=f"HTTP {status}")
                if tentativa == 2 or (status is not None and status < 500 and status != 429):
                    return Resultado(False, erro=str(e)[:300])
                time.sleep(2)
            except Exception as e:  # rede, DNS, timeout
                if tentativa == 2:
                    return Resultado(False, erro=f"{type(e).__name__}: {e}"[:300])
                time.sleep(2)
        return Resultado(False, erro="falha desconhecida")


def _elegiveis(s: Session, estacao: Estacao, faixa: Faixa) -> list[Inscricao]:
    minimo = ORDEM[faixa]
    return [
        i
        for i in s.scalars(
            select(Inscricao).where(
                Inscricao.ativa,
                (Inscricao.estacao_id.is_(None)) | (Inscricao.estacao_id == estacao.id),
            )
        )
        if i.faixa_minima in FAIXAS_VALIDAS and ORDEM[Faixa(i.faixa_minima)] <= minimo
    ]


def montar_abertura(
    est: Estacao, alerta: Alerta, nivel_m: float | None, tendencia: str | None
) -> dict[str, str]:
    rotulo = ROTULOS[alerta.faixa_nova]
    nivel = (
        f"Nível em {nivel_m:.2f}".replace(".", ",") + " m"
        if nivel_m is not None
        else "Nível acima do limite"
    )
    sentido = {"subindo": ", subindo", "descendo": ", descendo", "estavel": ", estável"}.get(
        tendencia or "", ""
    )
    origem = "Previsão" if alerta.origem == "previsto" else "Observado"
    return {
        "titulo": f"{est.curso_dagua or est.nome} em {rotulo}",
        "corpo": f"{nivel}{sentido}. {origem}. Fonte oficial: Defesa Civil de Presidente Getúlio.",
        "url": obter_configuracao().url_publica,
        "tag": f"alerta-{est.codigo}",
    }


def montar_encerramento(est: Estacao, nivel_m: float | None) -> dict[str, str]:
    nivel = f" Nível em {nivel_m:.2f}".replace(".", ",") + " m." if nivel_m is not None else ""
    return {
        "titulo": f"{est.curso_dagua or est.nome} voltou ao normal",
        "corpo": f"{nivel.strip()} Fonte oficial: Defesa Civil de Presidente Getúlio.".strip(),
        "url": obter_configuracao().url_publica,
        "tag": f"alerta-{est.codigo}",
    }


def _registrar(s: Session, alerta_id: int, i: Inscricao, tipo: str, r: Resultado) -> None:
    if r.expirada:
        i.ativa = False
    s.add(
        Notificacao(
            alerta_id=alerta_id,
            inscricao_id=i.id,
            tipo=tipo,
            status="enviada" if r.ok else ("expirada" if r.expirada else "falha"),
            erro=r.erro,
        )
    )


def notificar_abertura(
    s: Session,
    est: Estacao,
    alerta: Alerta,
    enviador: Enviador,
    nivel_m: float | None = None,
    tendencia: str | None = None,
) -> int:
    """Envia a abertura aos elegiveis. Devolve quantos receberam."""
    payload = montar_abertura(est, alerta, nivel_m, tendencia)
    enviados = 0
    for i in _elegiveis(s, est, Faixa(alerta.faixa_nova)):
        r = enviador.enviar(i, payload)
        _registrar(s, alerta.id, i, "abertura", r)
        enviados += r.ok
        if not r.ok:
            log.warning("push falhou", extra={"extra_campos": {"inscricao": i.id, "erro": r.erro}})
    s.flush()
    return enviados


def notificar_encerramento(
    s: Session,
    est: Estacao,
    alerta_encerrado: Alerta,
    enviador: Enviador,
    nivel_m: float | None = None,
) -> int:
    """A2: avisa so quem recebeu a abertura de qualquer alerta deste episodio."""
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
        select(Inscricao)
        .join(Notificacao, Notificacao.inscricao_id == Inscricao.id)
        .where(
            Inscricao.ativa,
            Notificacao.alerta_id.in_(ids_do_episodio),
            Notificacao.tipo == "abertura",
            Notificacao.status == "enviada",
        )
        .distinct()
    ).all()
    payload = montar_encerramento(est, nivel_m)
    enviados = 0
    for i in alvos:
        r = enviador.enviar(i, payload)
        _registrar(s, alerta_encerrado.id, i, "encerramento", r)
        enviados += r.ok
    s.flush()
    return enviados
