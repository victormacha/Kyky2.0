"""Cérebro plugável: tenta os provedores em ordem e troca sozinho se um falhar.
Se o nome do modelo não existir mais, descobre um válido no próprio provedor."""
import json
from pathlib import Path
from openai import OpenAI, NotFoundError, RateLimitError
from . import vault

ROOT = Path(__file__).parent.parent
CFG = json.loads((ROOT / "providers.json").read_text(encoding="utf-8"))
CACHE_FILE = ROOT / "models_cache.json"  # apague este arquivo p/ forçar nova escolha

# modelos que não servem para conversa
EXCLUDE = ("embed", "whisper", "tts", "guard", "moderation", "ocr", "transcri", "realtime",
           "audio", "image", "imagen", "veo", "lyria", "aqa", "vibe", "voxtral", "safeguard",
           "robotics", "live", "rerank")


class Brain:
    def __init__(self):
        self._clients = {}
        try:
            self._cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            self._cache = {}

    def _save_cache(self):
        try:
            CACHE_FILE.write_text(json.dumps(self._cache, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _client(self, name):
        if name not in self._clients:
            key = vault.get_key(name)
            if not key:
                return None
            p = CFG["providers"][name]
            self._clients[name] = OpenAI(api_key=key, base_url=p["base_url"], timeout=90)
        return self._clients[name]

    def _choose(self, name, client, ignore=()):
        ids = [m.id.replace("models/", "") for m in client.models.list()]
        ids = [i for i in ids if i not in ignore and not any(x in i.lower() for x in EXCLUDE)]
        ids.sort(key=lambda i: (("preview" in i or "exp" in i), len(i)))
        for pref in CFG["providers"][name].get("prefer", []):
            for i in ids:
                if pref in i.lower():
                    return i
        return ids[0] if ids else None

    @staticmethod
    def _limpa(messages, name):
        """Só o Google aceita (e exige) 'extra_content' (assinatura de raciocínio do Gemini 3)."""
        if name == "google":
            return messages
        out = []
        for m in messages:
            if m.get("tool_calls"):
                m = {**m, "tool_calls": [{k: v for k, v in tc.items() if k != "extra_content"} for tc in m["tool_calls"]]}
            out.append(m)
        return out

    def _call(self, name, client, messages, tools=None):
        model = self._cache.get(name)
        tentados = set()
        rodizio = [m for m in CFG["providers"][name].get("models", []) if m != model]   # outros modelos com cota própria
        messages = self._limpa(messages, name)
        for _ in range(3 + len(rodizio)):
            if not model:
                model = self._choose(name, client, ignore=tentados)
                if not model:
                    raise RuntimeError("nenhum modelo de chat encontrado")
            try:
                kwargs = {"model": model, "messages": messages, "max_tokens": 3000}
                if tools:
                    kwargs["tools"] = tools
                r = client.chat.completions.create(**kwargs)
            except RateLimitError:
                if not rodizio:
                    raise
                model = rodizio.pop(0)            # cota deste modelo acabou: tenta o próximo da lista
                continue
            except NotFoundError:
                tentados.add(model)
                self._cache.pop(name, None)
                model = None
                continue
            self._cache[name] = model
            self._save_cache()
            return r.choices[0].message
        raise RuntimeError("nenhum modelo respondeu")

    def chat(self, messages, level="strong", skip=(), tools=None):
        """Retorna (mensagem, provedor). 'skip' evita provedores (útil p/ revisão cruzada)."""
        import time
        for rodada in range(3):                      # limite temporário (429): espera e tenta de novo
            erros, limite = [], False
            for name in CFG["routes"][level]:
                if name in skip:
                    continue
                client = self._client(name)
                if client is None:
                    continue
                try:
                    return self._call(name, client, messages, tools), name
                except Exception as e:
                    texto = f"{type(e).__name__} {str(e)[:90]}"
                    limite = limite or "429" in texto or "RateLimit" in texto
                    erros.append(f"{name}: {texto}")
            if not limite or rodada == 2:
                break
            print("  [aviso] todos os provedores no limite, esperando 25s para tentar de novo...", flush=True)
            time.sleep(25)
        raise RuntimeError("Nenhum provedor respondeu.\n  " + "\n  ".join(erros or ["sem chaves salvas"]))

    def ask(self, messages, level="strong", skip=()):
        msg, name = self.chat(messages, level, skip)
        return msg.content, name
