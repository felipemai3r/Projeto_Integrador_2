from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api import consultas
from api.deps import obter_agora, obter_sessao
from api.previsao import prever
from api.schemas import PrevisaoOut, SimulacaoIn

router = APIRouter(tags=["previsao"])
SessaoDep = Annotated[Session, Depends(obter_sessao)]
AgoraDep = Annotated[datetime, Depends(obter_agora)]


@router.get("/previsao/{codigo}", response_model=PrevisaoOut)
def previsao(codigo: str, s: SessaoDep, agora: AgoraDep) -> PrevisaoOut:
    """Estimativa do nivel para 1, 3, 6, 12 e 24 h, com incerteza (CDU02). So onde ha modelo
    publicado (RN07); nos demais horizontes diz que esta indisponivel e por que."""
    est = consultas.obter_estacao(s, codigo)
    if est is None:
        raise HTTPException(404, f"Estação {codigo} não encontrada")
    return prever(s, est, agora)


@router.post("/simulacao", response_model=PrevisaoOut)
def simulacao(dados: SimulacaoIn, s: SessaoDep, agora: AgoraDep) -> PrevisaoOut:
    """Cenario hipotetico (CDU03): "e se tivesse chovido X mm nesses pontos?". Nao altera dado."""
    est = consultas.obter_estacao(s, dados.estacao)
    if est is None:
        raise HTTPException(404, f"Estação {dados.estacao} não encontrada")
    if not 1 <= dados.janela_h <= 24:
        raise HTTPException(422, "A janela precisa ficar entre 1 e 24 horas.")
    if not dados.chuva_mm:
        raise HTTPException(422, "Informe a chuva em pelo menos um ponto.")
    for codigo, mm in dados.chuva_mm.items():
        if not 0 <= mm <= 400:
            raise HTTPException(422, f"A chuva em {codigo} precisa ficar entre 0 e 400 mm.")
    return prever(s, est, agora, chuva_mm=dados.chuva_mm, janela_h=dados.janela_h)
