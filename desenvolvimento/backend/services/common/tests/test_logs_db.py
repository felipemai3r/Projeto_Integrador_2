"""Log estruturado em JSON e sessao com commit/rollback."""

import json
import logging
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from common import db
from common.logs import FormatadorJson, configurar
from common.models import Fonte


def registro(msg: str = "ola", extra: dict | None = None, exc: bool = False) -> logging.LogRecord:
    info = None
    if exc:
        try:
            raise ValueError("deu ruim")
        except ValueError:
            import sys

            info = sys.exc_info()
    r = logging.LogRecord("ingestor.pdc", logging.WARNING, __file__, 1, msg, None, info)
    r.created = datetime(2026, 11, 5, 12, 0, tzinfo=UTC).timestamp()
    if extra is not None:
        r.extra_campos = extra
    return r


def test_linha_e_um_json_com_horario_utc_nivel_logger_e_mensagem() -> None:
    evento = json.loads(FormatadorJson().format(registro()))
    assert evento == {
        "ts": "2026-11-05T12:00:00+00:00",
        "nivel": "WARNING",
        "logger": "ingestor.pdc",
        "msg": "ola",
    }


def test_campos_extras_entram_no_mesmo_nivel_e_acentos_ficam_legiveis() -> None:
    texto = FormatadorJson().format(
        registro("coleta concluída", {"fonte": "pdc_municipal", "n": 3})
    )
    assert "concluída" in texto and "\\u00" not in texto
    evento = json.loads(texto)
    assert evento["fonte"] == "pdc_municipal" and evento["n"] == 3


def test_valor_nao_serializavel_nos_extras_vira_texto_em_vez_de_quebrar() -> None:
    evento = json.loads(
        FormatadorJson().format(registro(extra={"quando": datetime(2026, 1, 1, tzinfo=UTC)}))
    )
    assert evento["quando"].startswith("2026-01-01")


def test_excecao_vai_no_campo_erro_com_a_pilha() -> None:
    evento = json.loads(FormatadorJson().format(registro(exc=True)))
    assert "ValueError: deu ruim" in evento["erro"]


def test_sem_excecao_nao_ha_campo_erro() -> None:
    assert "erro" not in json.loads(FormatadorJson().format(registro()))


def test_configurar_troca_os_handlers_da_raiz_e_aceita_nivel_em_qualquer_caixa() -> None:
    raiz = logging.getLogger()
    antes, nivel_antes = raiz.handlers[:], raiz.level
    try:
        configurar("warning")
        assert raiz.level == logging.WARNING and len(raiz.handlers) == 1
        assert isinstance(raiz.handlers[0].formatter, FormatadorJson)
    finally:
        raiz.handlers = antes
        raiz.setLevel(nivel_antes)


def test_sessao_confirma_ao_sair_sem_erro(s: Session) -> None:
    db.obter_engine.cache_clear()
    with db.sessao() as nova:
        nova.add(Fonte(codigo="f_ok", nome="n", base_url="u", frequencia_s=1))
    assert s.scalar(select(func.count()).select_from(Fonte).where(Fonte.codigo == "f_ok")) == 1


def test_sessao_desfaz_tudo_se_o_bloco_levantar_excecao(s: Session) -> None:
    with pytest.raises(RuntimeError), db.sessao() as nova:
        nova.add(Fonte(codigo="f_erro", nome="n", base_url="u", frequencia_s=1))
        nova.flush()
        raise RuntimeError("falha no meio")
    assert s.scalar(select(func.count()).select_from(Fonte).where(Fonte.codigo == "f_erro")) == 0
