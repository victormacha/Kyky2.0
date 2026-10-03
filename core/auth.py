"""Autenticação local da Kyky: senha (PBKDF2) e voz (frase falada + impressão espectral).
A voz é só uma CONVENIÊNCIA: pode ser imitada ou gravada, por isso ações críticas exigem a senha."""
import hashlib
import hmac
import json
import math
import os
import secrets
import time
from pathlib import Path

FILE = Path(os.environ.get("KYKY_AUTH") or Path(__file__).parent.parent / "data" / "auth.json")
FILE.parent.mkdir(exist_ok=True)
_sessions = {}
_falhas = {"n": 0, "ate": 0.0}


def _load():
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(d):
    FILE.write_text(json.dumps(d), encoding="utf-8")


def _hash(pw, salt):
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 200_000).hex()


def has_password():
    return "pw" in _load()


def has_voice():
    return "phrases" in _load().get("voice", {})


def set_password(pw):
    d = _load()
    salt = secrets.token_hex(16)
    d["pw"] = {"salt": salt, "hash": _hash(pw, salt)}
    _save(d)


def _limite():
    return time.time() < _falhas["ate"]


def _falhou():
    _falhas["n"] += 1
    if _falhas["n"] >= 5:
        _falhas["n"], _falhas["ate"] = 0, time.time() + 30


def check_password(pw):
    if _limite():
        return False
    p = _load().get("pw")
    ok = bool(p) and hmac.compare_digest(_hash(pw or "", p["salt"]), p["hash"])
    if ok:
        _falhas["n"] = 0
    else:
        _falhou()
    return ok


def _norm(t):
    return "".join(c for c in (t or "").lower() if c.isalnum() or c == " ").strip()


def _cos(a, b):
    num = sum(x * y for x, y in zip(a, b))
    den = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return num / den if den else 0.0


def _sim(a, b):
    if not a or not b:
        return 0.0
    d = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        p, d[0] = d[0], i
        for j, cb in enumerate(b, 1):
            p, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, p + (ca != cb))
    return 1 - d[len(b)] / max(len(a), len(b))


def enroll_voice(phrases, samples):
    """phrases: frase digitada + o que o Whisper entendeu em cada gravação. samples: 3 vetores."""
    phrases = [p for p in (_norm(x) for x in phrases) if p]
    if len(samples) < 3 or not phrases:
        return False
    mean = [sum(c) / len(samples) for c in zip(*samples)]
    piso = min(_cos(s, mean) for s in samples)
    d = _load()
    d["voice"] = {"phrases": phrases, "mean": mean, "min": piso}
    _save(d)
    return True


def check_voice(phrase, vector):
    v = _load().get("voice")
    if not v or "phrases" not in v or _limite() or not vector or len(vector) != len(v["mean"]):
        return False
    iguais = any(_sim(_norm(phrase), p) >= 0.6 for p in v["phrases"])
    ok = iguais and _cos(vector, v["mean"]) >= max(0.75, v["min"] - 0.08)
    if ok:
        _falhas["n"] = 0
    else:
        _falhou()
    return ok


SESSOES = FILE.parent / "sessions.json"   # só o hash do token fica no disco
VALIDADE = 12 * 3600                        # login lembrado por 12 horas (ações críticas sempre pedem a senha)


def _h(token):
    return hashlib.sha256((token or "").encode()).hexdigest()


def _carregar_sessoes():
    try:
        d = json.loads(SESSOES.read_text(encoding="utf-8"))
    except Exception:
        d = {}
    agora = time.time()
    return {k: v for k, v in d.items() if agora - v < VALIDADE}


def new_session():
    t = secrets.token_urlsafe(32)
    d = _carregar_sessoes()
    d[_h(t)] = time.time()
    _sessions[_h(t)] = d[_h(t)]
    try:
        SESSOES.write_text(json.dumps(d), encoding="utf-8")
    except Exception:
        pass
    return t


def valid(token):
    if not token:
        return False
    criado = _sessions.get(_h(token))
    if criado is None:                     # servidor reiniciou: confere as sessões salvas
        _sessions.update(_carregar_sessoes())
        criado = _sessions.get(_h(token))
    return criado is not None and time.time() - criado < VALIDADE
