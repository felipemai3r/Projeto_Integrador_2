"""Gera um par de chaves VAPID para Web Push. Rode UMA vez e guarde no .env (nunca no Git).

Uso: python -m api.gerar_vapid
"""

import base64

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid


def principal() -> None:
    v = Vapid()
    v.generate_keys()
    publica = v.public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    der = v.private_key.private_bytes(
        serialization.Encoding.DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    print("Cole no .env:")
    print("VAPID_PUBLIC_KEY=" + base64.urlsafe_b64encode(publica).rstrip(b"=").decode())
    print("VAPID_PRIVATE_KEY=" + base64.urlsafe_b64encode(der).rstrip(b"=").decode())


if __name__ == "__main__":
    principal()
