"""Configuracao: padroes seguros, leitura do ambiente e ausencia de segredo no exemplo."""

from pathlib import Path

import pytest

from common.config import Configuracao

EXEMPLO = Path(__file__).resolve().parents[4] / ".env.example"


def limpa(monkeypatch: pytest.MonkeyPatch) -> None:
    for chave in ("PDC_API_KEY", "PDC_API_URL", "JWT_SECRET", "DESATUALIZADO_APOS_MIN"):
        monkeypatch.delenv(chave, raising=False)


def test_chave_do_painel_municipal_vem_vazia_por_padrao(monkeypatch: pytest.MonkeyPatch) -> None:
    limpa(monkeypatch)
    cfg = Configuracao(_env_file=None)
    assert cfg.pdc_api_key == ""  # vazia: o coletor do painel nao e agendado


def test_url_do_painel_municipal_nao_carrega_credencial(monkeypatch: pytest.MonkeyPatch) -> None:
    limpa(monkeypatch)
    url = Configuracao(_env_file=None).pdc_api_url.lower()
    assert url.startswith("https://") and "key" not in url and "token" not in url and "@" not in url


def test_variaveis_de_ambiente_sobrescrevem_o_padrao(monkeypatch: pytest.MonkeyPatch) -> None:
    limpa(monkeypatch)
    monkeypatch.setenv("PDC_API_KEY", "valor-ficticio")
    monkeypatch.setenv("DESATUALIZADO_APOS_MIN", "45")
    cfg = Configuracao(_env_file=None)
    assert cfg.pdc_api_key == "valor-ficticio" and cfg.desatualizado_apos_min == 45


def test_nome_da_variavel_nao_diferencia_maiusculas(monkeypatch: pytest.MonkeyPatch) -> None:
    limpa(monkeypatch)
    monkeypatch.setenv("pdc_api_url", "https://outro.test/api")
    assert Configuracao(_env_file=None).pdc_api_url == "https://outro.test/api"


def test_variavel_desconhecida_no_ambiente_nao_quebra(monkeypatch: pytest.MonkeyPatch) -> None:
    limpa(monkeypatch)
    monkeypatch.setenv("VARIAVEL_QUE_NAO_EXISTE", "1")
    Configuracao(_env_file=None)


def test_limite_de_dado_desatualizado_padrao_e_de_30_minutos(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limpa(monkeypatch)
    assert Configuracao(_env_file=None).desatualizado_apos_min == 30


def test_exemplo_de_ambiente_declara_a_chave_do_painel_sem_valor() -> None:
    linhas = [ln.strip() for ln in EXEMPLO.read_text().splitlines()]
    atribuicoes = [ln for ln in linhas if ln.startswith("PDC_API_KEY")]
    assert atribuicoes == ["PDC_API_KEY="], "o exemplo nao pode trazer a chave real (RNF09)"


def test_exemplo_de_ambiente_nao_traz_segredos_de_verdade() -> None:
    suspeitos = ("BEGIN PRIVATE KEY", "eyJ", "sk-", "AKIA")
    texto = EXEMPLO.read_text()
    assert not any(s in texto for s in suspeitos)
