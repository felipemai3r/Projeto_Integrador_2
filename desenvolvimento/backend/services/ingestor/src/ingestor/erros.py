class FonteIndisponivel(Exception):
    """A fonte nao respondeu, estourou o tempo ou devolveu erro HTTP."""


class ChaveRecusada(FonteIndisponivel):
    """A fonte recusou a credencial (HTTP 401/403): repetir a chamada so gasta o limite da fonte."""


class ContratoQuebrado(Exception):
    """A resposta chegou, mas nao tem a estrutura esperada (a fonte mudou)."""
