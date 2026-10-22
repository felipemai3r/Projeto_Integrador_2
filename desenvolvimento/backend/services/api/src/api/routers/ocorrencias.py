import hashlib
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any

from common.config import obter_configuracao
from common.geo import dentro_do_municipio
from common.models import Moderacao, Ocorrencia, ReacaoOcorrencia, Usuario
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
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from api.contexto import contexto_hidrologico
from api.deps import obter_agora, obter_sessao
from api.fotos import FotoInvalida, tratar_e_salvar
from api.limite import LimiteTaxa, exigir, ip_do_cliente
from api.schemas import (
    MOTIVOS_DENUNCIA,
    TIPOS_IMPACTO,
    ModeracaoIn,
    ModeracaoOut,
    OcorrenciaCriada,
    OcorrenciaOut,
    ReacaoIn,
    ReacaoOut,
)
from api.seguranca import exigir_moderador, usuario_opcional

router = APIRouter(prefix="/ocorrencias", tags=["ocorrencias"])
limite_registro = LimiteTaxa(obter_configuracao().limite_registros_hora, timedelta(hours=1))
limite_reacao = LimiteTaxa(60, timedelta(hours=1))
# com isso, um registro ainda nao conferido sai do mapa publico ate a moderacao olhar
DENUNCIAS_PARA_OCULTAR = 3

SessaoDep = Annotated[Session, Depends(obter_sessao)]
AgoraDep = Annotated[datetime, Depends(obter_agora)]
STATUS = ("pendente", "validada", "rejeitada")


class Reacoes:
    """Curtidas e denuncias por registro, contadas numa unica consulta."""

    def __init__(self, s: Session, ids: list[int]) -> None:
        self.curtidas: dict[int, int] = defaultdict(int)
        self.motivos: dict[int, list[str]] = defaultdict(list)
        if ids:
            for r in s.scalars(
                select(ReacaoOcorrencia).where(ReacaoOcorrencia.ocorrencia_id.in_(ids))
            ):
                if r.tipo == "curtida":
                    self.curtidas[r.ocorrencia_id] += 1
                else:
                    self.motivos[r.ocorrencia_id].append(r.motivo or "outro")

    def denuncias(self, id_: int) -> int:
        return len(self.motivos[id_])


def _saida(
    o: Ocorrencia,
    reacoes: Reacoes,
    moderador: bool = False,
    ocultar_conteudo: bool = False,
) -> OcorrenciaOut:
    """`ocultar_conteudo`: registro ainda nao conferido no mapa publico, sem texto nem foto."""
    return OcorrenciaOut(
        id=o.id,
        latitude=o.latitude,
        longitude=o.longitude,
        ocorreu_em=o.ocorreu_em,
        tipo_impacto=o.tipo_impacto,
        descricao=None if ocultar_conteudo else o.descricao,
        tem_foto=o.foto_path is not None and not ocultar_conteudo,
        status=o.status,
        contexto=o.contexto,
        criada_em=o.criada_em,
        moderado_por=o.moderado_por if moderador else None,
        moderado_em=o.moderado_em if moderador else None,
        curtidas=reacoes.curtidas[o.id],
        denuncias=reacoes.denuncias(o.id) if moderador else None,
        motivos_denuncia=reacoes.motivos[o.id] if moderador else None,
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
            "Recebemos o seu registro. Ele já aparece no mapa como aguardando conferência, "
            "até a Defesa Civil conferir."
        ),
    )


@router.get("", response_model=list[OcorrenciaOut])
def listar(
    s: SessaoDep,
    agora: AgoraDep,
    usuario: Annotated[Usuario | None, Depends(usuario_opcional)],
    status: str = "validada",
    dias: Annotated[int, Query(ge=1, le=3650)] = 365,
    horas: Annotated[int | None, Query(ge=1, le=87600)] = None,
    com_pendentes: bool = False,
) -> list[OcorrenciaOut]:
    """Publico: so validadas. Pendentes e rejeitadas exigem login de quem modera.

    `com_pendentes` (so com status=validada) inclui no mapa os avisos ainda nao conferidos,
    para sinalizar na hora; para o publico eles vao sem descricao e sem foto. Um pendente com
    muitas denuncias sai do mapa publico ate a moderacao olhar. `horas` substitui `dias`.
    """
    if status not in STATUS:
        raise HTTPException(422, "Status inválido.")
    if status != "validada" and usuario is None:
        raise HTTPException(401, "Entre para ver registros em análise.")
    status_incluidos = (
        ["validada", "pendente"] if com_pendentes and status == "validada" else [status]
    )
    linhas = s.scalars(
        select(Ocorrencia)
        .where(
            Ocorrencia.status.in_(status_incluidos),
            Ocorrencia.ocorreu_em
            >= agora - (timedelta(hours=horas) if horas else timedelta(days=dias)),
        )
        .order_by(Ocorrencia.ocorreu_em.desc())
        .limit(500)
    ).all()
    reacoes = Reacoes(s, [o.id for o in linhas])
    publico = usuario is None
    return [
        _saida(
            o,
            reacoes,
            moderador=not publico,
            ocultar_conteudo=o.status == "pendente" and publico,
        )
        for o in linhas
        if not (
            publico and o.status == "pendente" and reacoes.denuncias(o.id) >= DENUNCIAS_PARA_OCULTAR
        )
    ]


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
    return _saida(o, Reacoes(s, [o.id]), moderador=True)


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


def _chave_do_aparelho(dispositivo: str) -> str:
    """Hash do identificador do navegador: impede reacao repetida sem guardar quem e."""
    sal = obter_configuracao().jwt_secret
    return hashlib.sha256(f"{sal}:{dispositivo}".encode()).hexdigest()


def _obter_visivel(s: Session, id_: int) -> Ocorrencia:
    o = _obter(s, id_)
    if o.status == "rejeitada":
        raise HTTPException(404, "Registro não encontrado.")
    return o


@router.post("/{id_}/reacoes", response_model=ReacaoOut)
def reagir(id_: int, dados: ReacaoIn, req: Request, s: SessaoDep, agora: AgoraDep) -> ReacaoOut:
    """Curtir ("vi tambem") ou denunciar, sem login. Uma de cada por aparelho; repetir nao soma."""
    exigir(limite_reacao, ip_do_cliente(req), agora)
    o = _obter_visivel(s, id_)
    if dados.tipo not in ("curtida", "denuncia"):
        raise HTTPException(422, "Reação inválida.")
    motivo = None
    if dados.tipo == "denuncia":
        if dados.motivo not in MOTIVOS_DENUNCIA:
            raise HTTPException(422, "Escolha o motivo da denúncia.")
        motivo = dados.motivo
    chave = _chave_do_aparelho(dados.dispositivo)
    existe = s.scalar(
        select(ReacaoOcorrencia).where(
            ReacaoOcorrencia.ocorrencia_id == o.id,
            ReacaoOcorrencia.tipo == dados.tipo,
            ReacaoOcorrencia.chave_hash == chave,
        )
    )
    if existe is None:
        s.add(
            ReacaoOcorrencia(ocorrencia_id=o.id, tipo=dados.tipo, chave_hash=chave, motivo=motivo)
        )
        s.flush()
    return ReacaoOut(curtidas=Reacoes(s, [o.id]).curtidas[o.id])


@router.delete("/{id_}/reacoes", response_model=ReacaoOut)
def desfazer(id_: int, dados: ReacaoIn, s: SessaoDep) -> ReacaoOut:
    """Desfaz a curtida ou a denuncia deste aparelho."""
    o = _obter_visivel(s, id_)
    s.execute(
        delete(ReacaoOcorrencia).where(
            ReacaoOcorrencia.ocorrencia_id == o.id,
            ReacaoOcorrencia.tipo == dados.tipo,
            ReacaoOcorrencia.chave_hash == _chave_do_aparelho(dados.dispositivo),
        )
    )
    s.flush()
    return ReacaoOut(curtidas=Reacoes(s, [o.id]).curtidas[o.id])
