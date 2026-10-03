"""Mostra os modelos disponíveis em cada provedor, p/ você ajustar o providers.json."""
from openai import OpenAI
from core import vault
from core.brain import CFG

for name, p in CFG["providers"].items():
    key = vault.get_key(name)
    if not key:
        print(f"\n[{name}] sem chave"); continue
    try:
        ids = sorted(m.id for m in OpenAI(api_key=key, base_url=p["base_url"]).models.list())
        print(f"\n[{name}] modelo preferido: {p.get('prefer', ['?'])[0]}")
        print("  " + "\n  ".join(ids[:40]))
    except Exception as e:
        print(f"\n[{name}] erro: {type(e).__name__}")
