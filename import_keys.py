"""Importa suas chaves de um arquivo de texto para o cofre do Windows.
As chaves NÃO vão para o código. Formato de cada linha:  <chave> - <provedor>
Uso:  python import_keys.py            (lê keys.txt na pasta do projeto)
      python import_keys.py outro.txt"""
import sys
from pathlib import Path
from core import vault
from core.brain import CFG

ALIAS = {"gemini": "google", "google": "google"}

arquivo = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "keys.txt"
if not arquivo.exists():
    sys.exit(f"Arquivo não encontrado: {arquivo}")

importadas = []
for linha in arquivo.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
    if " - " not in linha:
        continue
    chave, provedor = linha.rsplit(" - ", 1)
    nome = provedor.strip().lower()
    nome = ALIAS.get(nome, nome)
    if nome in CFG["providers"] and chave.strip():
        vault.set_key(nome, chave.strip())
        importadas.append(nome)
    else:
        print(f"Ignorado (provedor desconhecido): {provedor.strip()}")
print("Importadas:", ", ".join(importadas) or "nenhuma")
