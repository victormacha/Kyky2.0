"""Rode uma vez: guarda suas chaves no cofre do Windows (a digitação fica oculta)."""
import getpass
from core import vault
from core.brain import CFG

for name in CFG["providers"]:
    estado = "já salva" if vault.get_key(name) else "vazia"
    key = getpass.getpass(f"Chave {name} ({estado}) - Enter para pular: ").strip()
    if key:
        vault.set_key(name, key)
        print("  guardada.")
print("Pronto.")
