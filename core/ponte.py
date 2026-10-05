"""Ponte PC <-> celular.
PC -> celular: os arquivos ficam em data/ponte até o celular baixar (o app avisa quando chega um novo).
Celular -> PC: o que o celular envia cai na pasta 'Do celular' na Área de Trabalho."""
import base64
import json
import re
import shutil
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
SAIDA = ROOT / "data" / "ponte"                     # esperando o celular baixar
ENTRADA = Path.home() / "Desktop" / "Do celular"     # o que veio do celular
LIMITE = 50 * 1024 * 1024                            # 50 MB por arquivo
avisar = None   # o server.py liga isto a uma função que avisa as janelas abertas (celular/PC)


def _nome(n):
    """Nome de arquivo seguro (sem pastas, sem caracteres proibidos no Windows/Android)."""
    n = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", Path(str(n)).name).strip(" .")
    return n[:120] or f"arquivo-{time.strftime('%Y%m%d-%H%M%S')}"


def _livre(pasta, nome):
    """Não sobrescreve: 'foto.jpg' vira 'foto (2).jpg' se já existir."""
    p, i = pasta / nome, 2
    while p.exists():
        p = pasta / f"{Path(nome).stem} ({i}){Path(nome).suffix}"
        i += 1
    return p


def _meta():
    try:
        return json.loads((SAIDA / ".meta.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def _salva_meta(m):
    (SAIDA / ".meta.json").write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------- PC -> celular
def send_to_phone(path="", content="", name="", nota=""):
    """Manda um arquivo do PC para o celular. Use 'path' para um arquivo que já existe,
    ou 'content' + 'name' para criar um arquivo de texto novo direto no celular."""
    from .tools import _resolve
    SAIDA.mkdir(parents=True, exist_ok=True)
    if path:
        origem = _resolve(path)
        if not origem.is_file():
            return f"arquivo não encontrado: {origem}"
        if origem.stat().st_size > LIMITE:
            return "arquivo grande demais para a ponte (máximo 50 MB)"
        destino = _livre(SAIDA, _nome(name or origem.name))
        shutil.copy2(origem, destino)
    elif content:
        destino = _livre(SAIDA, _nome(name or "nota.txt"))
        destino.write_text(content, encoding="utf-8")
    else:
        return "erro: informe 'path' (arquivo existente) ou 'content' (texto do arquivo novo)"
    m = _meta()
    m[destino.name] = {"nota": nota, "quando": time.time()}
    _salva_meta(m)
    if avisar:
        avisar("mobile", {"type": "ponte", "name": destino.name, "nota": nota})
    return f"enviado para o celular: {destino.name} (aparece na aba Ponte do app; se o app estiver aberto, ele avisa na hora)"


def pendentes():
    SAIDA.mkdir(parents=True, exist_ok=True)
    m = _meta()
    itens = [p for p in SAIDA.iterdir() if p.is_file() and not p.name.startswith(".")]
    itens.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [{"name": p.name, "size": p.stat().st_size, "quando": p.stat().st_mtime,
             "nota": m.get(p.name, {}).get("nota", "")} for p in itens]


def arquivo_saida(nome):
    p = SAIDA / _nome(nome)
    return p if p.is_file() and not p.name.startswith(".") else None


def apagar_saida(nome):
    p = arquivo_saida(nome)
    if p:
        p.unlink()
        m = _meta()
        m.pop(p.name, None)
        _salva_meta(m)
    return bool(p)


def enviar_bytes(nome, dados_b64, nota=""):
    """PC -> celular a partir da aba Ponte (arquivo escolhido na tela do PC)."""
    dados = base64.b64decode(dados_b64)
    if len(dados) > LIMITE:
        raise ValueError("arquivo grande demais (máximo 50 MB)")
    SAIDA.mkdir(parents=True, exist_ok=True)
    p = _livre(SAIDA, _nome(nome))
    p.write_bytes(dados)
    m = _meta()
    m[p.name] = {"nota": nota, "quando": time.time()}
    _salva_meta(m)
    if avisar:
        avisar("mobile", {"type": "ponte", "name": p.name, "nota": nota})
    return p


# ---------------------------------------------------------------- celular -> PC
def receber(nome, dados_b64):
    dados = base64.b64decode(dados_b64)
    if len(dados) > LIMITE:
        raise ValueError("arquivo grande demais (máximo 50 MB)")
    ENTRADA.mkdir(parents=True, exist_ok=True)
    p = _livre(ENTRADA, _nome(nome))
    p.write_bytes(dados)
    if avisar:
        avisar("pc", {"type": "ponte_pc", "name": p.name})
    return p


def phone_files(limit=30):
    """Lista o que o celular mandou para o PC (pasta 'Do celular' na Área de Trabalho)."""
    if not ENTRADA.exists():
        return "nada recebido do celular ainda"
    itens = sorted((p for p in ENTRADA.iterdir() if p.is_file()), key=lambda p: p.stat().st_mtime, reverse=True)
    return f"pasta: {ENTRADA}\n" + "\n".join(
        f"{p.name} ({p.stat().st_size // 1024} KB, {time.strftime('%d/%m %H:%M', time.localtime(p.stat().st_mtime))})"
        for p in itens[:int(limit)]) if itens else "nada recebido do celular ainda"
