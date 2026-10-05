"""Quem é o dono desta Kyky (arquivo dono.json na pasta principal).
É o que permite a MESMA Kyky (mesmo código, mesmas atualizações) servir pessoas diferentes."""
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
ARQUIVO = ROOT / "dono.json"

# grupos de recursos que podem ser ligados/desligados por dono
TODOS = ["github", "leads", "vagas", "canvas", "email", "instagram"]
PADRAO = {
    "nome": "você",
    "sobre": "",                 # 1-2 frases usadas no modo rápido/código (o perfil completo fica em profile.md)
    "repo_proprio": "",          # repositório onde a Kyky deste dono se publica (dono/nome)
    "cidade_exemplo": "sua cidade",
    "recursos": TODOS,
}


def _carregar():
    try:
        return {**PADRAO, **json.loads(ARQUIVO.read_text(encoding="utf-8"))}
    except Exception:
        return dict(PADRAO)


DONO = _carregar()
NOME = DONO["nome"]


def tem(recurso):
    return recurso in DONO["recursos"]


def publico():
    """O que a interface precisa saber (nada sensível)."""
    return {"nome": NOME, "recursos": DONO["recursos"], "cidade_exemplo": DONO["cidade_exemplo"]}
