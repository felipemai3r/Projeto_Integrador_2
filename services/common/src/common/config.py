"""Configuracao lida de variaveis de ambiente. Unico ponto de leitura do ambiente."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Configuracao(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://pgetulio:troque_esta_senha@localhost:5432/pgetulio"
    log_level: str = "INFO"

    dcsc_graphql_url: str = "https://monitoramento.defesacivil.sc.gov.br/graphql"
    dcsc_rest_url: str = "https://api-dcsc.mks-unifique.ddns.net"
    openmeteo_forecast_url: str = "https://api.open-meteo.com/v1/forecast"
    openmeteo_archive_url: str = "https://archive-api.open-meteo.com/v1/archive"


@lru_cache
def obter_configuracao() -> Configuracao:
    return Configuracao()
