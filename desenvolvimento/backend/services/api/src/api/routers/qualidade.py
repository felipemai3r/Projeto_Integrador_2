from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.deps import obter_agora, obter_sessao
from api.qualidade import qualidade_das_estacoes, qualidade_das_fontes
from api.schemas import Qualidade

router = APIRouter(prefix="/qualidade", tags=["operacao"])


@router.get("", response_model=Qualidade)
def qualidade(
    s: Annotated[Session, Depends(obter_sessao)], agora: Annotated[datetime, Depends(obter_agora)]
) -> Qualidade:
    """Cobertura por estacao, lacunas, sensor travado e fontes instaveis (RF36, RNF16)."""
    return Qualidade(
        gerado_em=agora,
        fontes=qualidade_das_fontes(s),
        estacoes=qualidade_das_estacoes(s, agora),
    )
