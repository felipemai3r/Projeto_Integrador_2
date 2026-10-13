from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any

from common.config import obter_configuracao
from common.geo import dentro_do_municipio
from common.models import Moderacao, Ocorrencia, Usuario
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.contexto import contexto_hidrologico
from api.deps import obter_agora, obter_sessao
from api.fotos import FotoInvalida, tratar_e_salvar
from api.limite import LimiteTaxa, exigir, ip_do_cliente
from api.schemas import (
    TIPOS_IMPACTO,
    ModeracaoIn,
    ModeracaoOut,
    OcorrenciaCriada,
    OcorrenciaOut,
)
from api.seguranca import exigir_moderador, usuario_opcional

router = APIRouter(prefix="/ocorrencias", tags=["ocorrencias"])
limite_registro = LimiteTaxa(obter_configuracao().limite_registros_hora, timedelta(hours=1))

SessaoDep = Annotated[Session, Depends(obter_sessao)]
AgoraDep = Annotated[datetime, Depends(obter_agora)]
STATUS = ("pendente", "validada", "rejeitada")


def _saida(o: Ocorrencia, moderador: bool = False) -> OcorrenciaOut:
    return OcorrenciaOut(
        id=o.id,
        latitude=o.latitude,
        longitude=o.longitude,
        ocorreu_em=o.ocorreu_em,
        tipo_impacto=o.tipo_impacto,
        descricao=o.descricao,
        tem_foto=o.foto_path is not None,
        status=o.status,
        contexto=o.contexto,
        criada_em=o.criada_em,
        moderado_por=o.moderado_por if moderador else None,
        moderado_em=o.moderado_em if moderador else None,
    )


@router.post("", response_model=OcorrenciaCriada, status_code=201)
async def registrar(
    req: Request,
    s: SessaoDep,
    agora: AgoraDep,
    latitude: Annotated[float, Form(ge=-90, le=90)],
    longitude: Annotated[float, Form(ge=-180, le=180)],
    ocorreu_em: Annotated[datetime, Form()],
    tipo_impacto: Annotated[str, Form()],
    descricao: Annotated[str | None, Form(max_length=500)] = None,
    foto: Annotated[UploadFile | None, File()] = None,
) -> OcorrenciaCriada:
    """Registro anonimo de alagamento (CDU04). Entra como pendente e passa por moderacao (RN05)."""
    exigir(limite_registro, ip_do_cliente(req), agora)
    if tipo_impacto not in TIPOS_IMPACTO:
        raise HTTPException(422, "Escolha o tipo de impacto.")
    if ocorreu_em.tzinfo is None:
        raise HTTPException(422, "Informe a data e a hora com o fuso horário.")
    ocorreu_em = ocorreu_em.astimezone(UTC)
    if ocorreu_em > agora + timedelta(minutes=5):
        raise HTTPException(422, "A data e a hora não podem estar no futuro.")
    if ocorreu_em < agora - timedelta(days=365):
        raise HTTPException(422, "Só aceitamos registros do último ano.")
    if not dentro_do_municipio(latitude, longitude):
        raise HTTPException(422, "O ponto precisa estar dentro de Presidente Getúlio.")

    nome_foto: str | None = None
    if foto is not None and foto.filename:
        try:
            nome_foto = tratar_e_salvar(
                await foto.read(), foto.content_type, obter_configuracao().pasta_fotos
            )
        except FotoInvalida as e:
            raise HTTPException(422, str(e)) from e

    o = Ocorrencia(
        latitude=latitude,
        longitude=longitude,
        ocorreu_em=ocorreu_em,
        tipo_impacto=tipo_impacto,
        descricao=(descricao or "").strip() or None,
        foto_path=nome_foto,
        status="pendente",
        contexto=contexto_hidrologico(s, ocorreu_em),
    )
    s.add(o)
    s.flush()
    return OcorrenciaCriada(
        id=o.id,
        status=o.status,
        mensagem=(
            "Recebemos o seu registro. Ele aparece no mapa depois que a Defesa Civil conferir."
        ),
    )


@router.get("", response_model=list[OcorrenciaOut])
def listar(
    s: SessaoDep,
    agora: AgoraDep,
    usuario: Annotated[Usuario | None, Depends(usuario_opcional)],
    status: str = "validada",
    dias: Annotated[int, Query(ge=1, le=3650)] = 365,
) -> list[OcorrenciaOut]:
    """Publico: so validadas. Pendentes e rejeitadas exigem login de quem modera."""
    if status not in STATUS:
        raise HTTPException(422, "Status inválido.")
    if status != "validada" and usuario is None:
        raise HTTPException(401, "Entre para ver registros em análise.")
    linhas = s.scalars(
        select(Ocorrencia)
        .where(Ocorrencia.status == status, Ocorrencia.ocorreu_em >= agora - timedelta(days=dias))
        .order_by(Ocorrencia.ocorreu_em.desc())
        .limit(500)
    )
    return [_saida(o, moderador=usuario is not None) for o in linhas]


def _obter(s: Session, id_: int) -> Ocorrencia:
    o = s.get(Ocorrencia, id_)
    if o is None:
        raise HTTPException(404, "Registro não encontrado.")
    return o


@router.get("/{id_}/foto")
def foto(
    id_: int, s: SessaoDep, usuario: Annotated[Usuario | None, Depends(usuario_opcional)]
) -> FileResponse:
    o = _obter(s, id_)
    if o.foto_path is None:
        raise HTTPException(404, "Este registro não tem foto.")
    if o.status != "validada" and usuario is None:
        raise HTTPException(404, "Registro não encontrado.")  # nao revela existencia
    caminho = Path(obter_configuracao().pasta_fotos) / o.foto_path
    if not caminho.is_file():
        raise HTTPException(404, "Foto indisponível.")
    return FileResponse(caminho, media_type="image/jpeg", headers={"Cache-Control": "private"})


@router.patch("/{id_}", response_model=OcorrenciaOut)
def moderar(
    id_: int,
    dados: ModeracaoIn,
    s: SessaoDep,
    moderador: Annotated[Usuario, Depends(exigir_moderador)],
) -> OcorrenciaOut:
    """Valida, rejeita ou reclassifica. Todo passo fica no historico (RF26)."""
    o = _obter(s, id_)
    status_novo, tipo_novo = o.status, o.tipo_impacto
    if dados.acao == "validar":
        status_novo = "validada"
    elif dados.acao == "rejeitar":
        if not (dados.nota or "").strip():
            raise HTTPException(422, "Explique o motivo da rejeição.")
        status_novo = "rejeitada"
    elif dados.acao == "reclassificar":
        if dados.tipo_impacto not in TIPOS_IMPACTO or dados.tipo_impacto == o.tipo_impacto:
            raise HTTPException(422, "Escolha um tipo de impacto diferente do atual.")
        tipo_novo = dados.tipo_impacto
    else:
        raise HTTPException(422, "Ação inválida.")

    s.add(
        Moderacao(
            ocorrencia_id=o.id,
            usuario_id=moderador.id,
            acao=dados.acao,
            status_anterior=o.status,
            status_novo=status_novo,
            tipo_anterior=o.tipo_impacto,
            tipo_novo=tipo_novo,
            nota=(dados.nota or "").strip() or None,
        )
    )
    o.status, o.tipo_impacto = status_novo, tipo_novo
    o.moderado_por, o.moderado_em = moderador.nome, datetime.now(UTC)
    s.flush()
    return _saida(o, moderador=True)


@router.get("/{id_}/historico", response_model=list[ModeracaoOut])
def historico(
    id_: int, s: SessaoDep, _: Annotated[Usuario, Depends(exigir_moderador)]
) -> list[ModeracaoOut]:
    _obter(s, id_)
    linhas: list[Any] = s.execute(
        select(Moderacao, Usuario)
        .join(Usuario, Usuario.id == Moderacao.usuario_id)
        .where(Moderacao.ocorrencia_id == id_)
        .order_by(Moderacao.em, Moderacao.id)
    ).all()
    return [
        ModeracaoOut(
            acao=m.acao,
            usuario=u.nome,
            status_anterior=m.status_anterior,
            status_novo=m.status_novo,
            tipo_anterior=m.tipo_anterior,
            tipo_novo=m.tipo_novo,
            nota=m.nota,
            em=m.em,
        )
        for m, u in linhas
    ]
