"""Cofre de chaves: Gerenciador de Credenciais do Windows, com as chaves embutidas
em core/secrets_local.py como reserva."""
import keyring

try:
    from .secrets_local import KEYS as _EMBUTIDAS
except ImportError:
    _EMBUTIDAS = {}

SERVICE = "kyky"


def set_key(name, key):
    keyring.set_password(SERVICE, name, key)


def get_key(name):
    try:
        key = keyring.get_password(SERVICE, name)
    except Exception:
        key = None
    return key or _EMBUTIDAS.get(name)
