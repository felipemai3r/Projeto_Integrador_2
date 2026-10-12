class FonteIndisponivel(Exception):
    """A fonte nao respondeu, estourou o tempo ou devolveu erro HTTP."""


class ContratoQuebrado(Exception):
    """A resposta chegou, mas nao tem a estrutura esperada (a fonte mudou)."""
