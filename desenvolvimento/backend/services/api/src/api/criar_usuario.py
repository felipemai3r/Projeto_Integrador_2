"""Cria (ou atualiza a senha de) um usuario de moderacao.

Uso: python -m api.criar_usuario --email fulano@exemplo.br --nome "Fulano" --papel moderador
A senha e pedida no terminal (nao fica no historico do shell) ou lida de SENHA_USUARIO.
"""

import argparse
import getpass
import os

from common.db import sessao
from common.models import Usuario
from sqlalchemy import select

from api.seguranca import PAPEIS, hash_senha


def principal() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--email", required=True)
    ap.add_argument("--nome", required=True)
    ap.add_argument("--papel", choices=PAPEIS, default="moderador")
    args = ap.parse_args()
    senha = os.environ.get("SENHA_USUARIO") or getpass.getpass("Senha: ")
    if len(senha) < 10:
        raise SystemExit("Use uma senha com pelo menos 10 caracteres.")
    email = args.email.strip().lower()
    with sessao() as s:
        u = s.scalar(select(Usuario).where(Usuario.email == email))
        if u is None:
            s.add(
                Usuario(nome=args.nome, email=email, papel=args.papel, senha_hash=hash_senha(senha))
            )
            print(f"usuario criado: {email} ({args.papel})")
        else:
            u.senha_hash, u.nome, u.papel, u.ativo = hash_senha(senha), args.nome, args.papel, True
            print(f"usuario atualizado: {email} ({args.papel})")


if __name__ == "__main__":
    principal()
