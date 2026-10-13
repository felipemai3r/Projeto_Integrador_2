"""Configuracao lida de variaveis de ambiente. Unico ponto de leitura do ambiente."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Configuracao(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://pgetulio:troque_esta_senha@localhost:5432/pgetulio"
    log_level: str = "INFO"
    cors_origens: str = "http://localhost:5173"
    # acima disso, a ultima leitura de uma estacao e marcada como desatualizada (RN04)
    desatualizado_apos_min: int = 30
    jwt_secret: str = "segredo-somente-para-testes-automatizados-0123456789"
    jwt_horas: int = 8
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = "mailto:equipe@exemplo.br"
    url_publica: str = "http://localhost:5173"
    pasta_fotos: str = "/tmp/fotos-ocorrencias"
    pasta_artefatos: str = "/tmp/artefatos-modelo"
    limite_registros_hora: int = 5
    avaliador_ativo: bool = False  # ligado no compose; desligado em testes

    dcsc_graphql_url: str = "https://monitoramento.defesacivil.sc.gov.br/graphql"
    dcsc_rest_url: str = "https://api-dcsc.mks-unifique.ddns.net"
    openmeteo_forecast_url: str = "https://api.open-meteo.com/v1/forecast"
    openmeteo_archive_url: str = "https://archive-api.open-meteo.com/v1/archive"


@lru_cache
def obter_configuracao() -> Configuracao:
    return Configuracao()
