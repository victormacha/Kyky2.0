"""Servidor local da Kyky (só 127.0.0.1): API + WebSocket + interface em web/."""
import asyncio
import webbrowser
import os
import base64
import re
import edge_tts
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from pydantic import BaseModel
from core import agent, auth, briefing, canvas, daily, github, jobs, leads, memory, tasks, tools, vault
from core.brain import Brain, CFG

BASE = Path(__file__).parent
app = FastAPI(title="Kyky")
brain = Brain()
history = memory.recent(20)
pool = ThreadPoolExecutor(8)

REGRAS_VOZ = (
    "\n\nVocê conversa por VOZ: respostas curtas, em frases corridas como numa conversa. NUNCA use emojis, risadas escritas (kkkk, skksksk, rsrs), listas, "
    "numeração, títulos, asteriscos, hashtags ou símbolos como #; para enumerar, fale em frases (primeiro, depois, por fim). "
    "Escreva seu nome como Kyky. Você tem ferramentas: acesso aos arquivos do PC do Victor (listar, ler, criar, abrir), "
    "terminal (run_command, pede confirmação), Python, pesquisa na web, tarefas, leads e fila "
    "de contato (nunca envia mensagens sozinha), Canvas da faculdade (só leitura), GitHub (listar e LER arquivos de repositórios com github_tree e github_read; nunca diga que um repositório está vazio sem listar a árvore completa) e vagas. Quando o Victor pedir para corrigir um bug em um projeto dele: (1) github_tree, (2) leia os arquivos relevantes com github_read (o código real, nunca chute), (3) ache a CAUSA exata, (4) prepare a correção com github_patch usando trechos exatos e mínimos e explique o motivo, (5) só então ofereça abrir o Pull Request com github_commit_patches, que ele precisa aprovar. Nunca afirme que algo está corrigido sem ter lido o código. Método: use github_grep para localizar, leia só trechos (start/end), registre cada descoberta com anotar e NÃO releia o que já anotou; conclua em até 12 passos de emprego (você só prepara a candidatura, nunca envia). "
    "Ações sensíveis pedem confirmação do dono; se negado, aceite sem insistir. "
    "NUNCA diga que fez algo (commit, push, criar arquivo, configurar) sem ter chamado a ferramenta e visto o resultado; "
    "se uma ferramenta falhar, conte o erro exato. Nunca mande o Victor rodar comandos que você mesma pode rodar."
    "\n\nARQUIVOS NO PC: caminho relativo vai para o seu workspace interno; quando o Victor pedir para criar, abrir ou "
    "salvar algo no computador dele, use SEMPRE caminho absoluto. Pastas dele: "
    + ", ".join(f"{n} = {p}" for n, p in tools.PASTAS.items()) +
    ". Se ele não disser onde salvar, use a Área de Trabalho (Desktop). Depois de criar um arquivo que ele vai querer ver, "
    "ofereça abrir com open_path. Para abrir um programa pelo nome (Spotify, Word, WhatsApp...) use open_app, nunca diga "
    "que não consegue abrir apps. Quando ele pedir para pesquisar algo NO GOOGLE ou no navegador dele, use google_search "
    "(abre no navegador dele); para você mesma pesquisar e responder, use web_search. "
    f"\nGITHUB: para criar repositório use github_create_repo; para enviar uma pasta para o GitHub use github_publish "
    f"(cria o repositório se faltar, faz commit e push). A sua própria pasta (o seu código) é {BASE}; o repositório "
    "oficial de você mesma é victormacha/Kyky2.0, então 'se publica no GitHub' = github_publish com essa pasta e esse repositório."
)


def e_codigo(texto):
    return bool(re.search(r"\b(bug|erro|corrig\w*|conserta\w*|reposit\w*|c[oó]digo|github|deploy|projeto)\b", texto, re.I))


def sistema(level, texto=""):
    """Perfil completo no modo forte; no rápido vai só o essencial (limites de tokens dos provedores gratuitos)."""
    base = (BASE / "personality.md").read_text(encoding="utf-8")
    codigo = re.search(r"\b(bug|erro|corrig\w*|conserta\w*|reposit\w*|c[oó]digo|github|deploy|projeto)\b", texto, re.I)
    if level == "fast" or codigo:
        perfil = "O dono se chama Victor, 18 anos, brasileiro, universitário. Fale informal e direto, vá ao ponto."
    else:
        arq = BASE / "profile.md"
        perfil = arq.read_text(encoding="utf-8") if arq.exists() else "O dono se chama Victor. Fale informal e direto."
    return base + "\n\n" + perfil + REGRAS_VOZ


def need_auth(authorization):
    if not authorization or not auth.valid(authorization.replace("Bearer ", "")):
        raise HTTPException(401, "não autenticado")


# ---------- autenticação ----------
class Senha(BaseModel):
    password: str


class Amostra(BaseModel):
    audio: str
    vector: list[float]


class VozEnroll(BaseModel):
    phrase: str
    samples: list[Amostra]


class VozLogin(BaseModel):
    audio: str
    vector: list[float]


class Audio(BaseModel):
    audio: str


_EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200d]")


def limpar(t):
    """Texto de voz: sem emoji, markdown, listas numeradas nem hashtags."""
    t = re.sub(r"```.*?```", " ", t, flags=re.S)
    t = _EMOJI.sub("", t)
    t = re.sub(r"^\s{0,3}#{1,6}\s*", "", t, flags=re.M)
    t = re.sub(r"(\*\*|__|`|~~)", "", t)
    t = re.sub(r"^\s*[-*•]\s+", "", t, flags=re.M)
    t = re.sub(r"^\s*\d+[.)]\s+", "", t, flags=re.M)
    t = re.sub(r"#(\d+)", r"número \1", t)
    t = re.sub(r"^\s*kyky\s*:\s*", "", t, flags=re.I)
    t = re.sub(r"\b(?:[sk]*k{2,}[sk]*|(?:sk){2,}k*|(?:ha|he|rs){2,}h*)\b", "", t, flags=re.I)  # risadas escritas
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r"\s+([.,!?;])", r"\1", t)
    t = re.sub(r"(?:[sk]*k{2,}[sk]*|(?:sk){2,}k*|(?:ha|he|rs){2,}h*)", "", t, flags=re.I)  # risadas escritas
    t = re.sub(r"[ 	]{2,}", " ", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def transcrever(b64):
    """Whisper (Groq): entende bem português e não depende do reconhecimento do navegador."""
    key = vault.get_key("groq")
    if not key:
        raise RuntimeError("sem chave do Groq")
    cli = OpenAI(api_key=key, base_url=CFG["providers"]["groq"]["base_url"], timeout=30)
    r = cli.audio.transcriptions.create(model="whisper-large-v3-turbo", file=("voz.webm", base64.b64decode(b64)),
                                        language="pt", prompt="Conversa com a Kyky, assistente do Victor.")
    return r.text.strip()


@app.post("/api/stt")
def api_stt(b: Audio, authorization: str = Header(None)):
    need_auth(authorization)
    try:
        return {"text": transcrever(b.audio)}
    except Exception as e:
        raise HTTPException(502, f"{type(e).__name__}: {str(e)[:160]}")


@app.get("/api/auth/state")
def auth_state():
    return {"has_password": auth.has_password(), "has_voice": auth.has_voice()}


@app.post("/api/auth/setup")
def auth_setup(b: Senha):
    if auth.has_password():
        raise HTTPException(403, "senha já definida")
    if len(b.password) < 6:
        raise HTTPException(400, "use ao menos 6 caracteres")
    auth.set_password(b.password)
    return {"token": auth.new_session()}


@app.post("/api/auth/login")
def auth_login(b: Senha):
    if not auth.check_password(b.password):
        raise HTTPException(401, "senha incorreta ou bloqueio temporário")
    return {"token": auth.new_session()}


@app.post("/api/auth/voice/enroll")
def voice_enroll(b: VozEnroll, authorization: str = Header(None)):
    need_auth(authorization)
    try:
        ouvido = [transcrever(s.audio) for s in b.samples]
    except Exception:
        raise HTTPException(502, "não consegui transcrever as gravações")
    if not auth.enroll_voice([b.phrase] + ouvido, [s.vector for s in b.samples]):
        raise HTTPException(400, "grave 3 amostras da frase")
    return {"ok": True, "ouvi": ouvido}


@app.post("/api/auth/voice/login")
def voice_login(b: VozLogin):
    try:
        texto = transcrever(b.audio)
    except Exception:
        raise HTTPException(502, "não consegui transcrever")
    if not auth.check_voice(texto, b.vector):
        raise HTTPException(401, "voz não reconhecida")
    return {"token": auth.new_session()}


# ---------- inicialização (animação de boot) ----------
def _check(fn):
    try:
        return {"ok": True, "detail": str(fn())[:60]}
    except Exception as e:
        return {"ok": False, "detail": f"{type(e).__name__}"}


@app.get("/api/status")
def status():
    provs = [n for n in CFG["providers"] if vault.get_key(n)]
    futs = {"canvas": pool.submit(_check, lambda: len(canvas._get("courses", enrollment_state="active")) + 0),
            "github": pool.submit(_check, lambda: github._get("user")["login"])}
    res = {}
    for k, f in futs.items():
        try:
            res[k] = f.result(timeout=10)
        except Exception:
            res[k] = {"ok": False, "detail": "timeout"}
    return {"providers": provs, "total_providers": len(CFG["providers"]),
            "search": bool(vault.get_key("tavily")), "memory": True, **res}


# ---------- painéis ----------
@app.get("/api/history")
def api_history(authorization: str = Header(None)):
    need_auth(authorization)
    return memory.recent(100)


@app.get("/api/tasks")
def api_tasks(authorization: str = Header(None)):
    need_auth(authorization)
    return {"text": tasks.list_tasks("all")}


@app.post("/api/tasks/{tid}/done")
def api_task_done(tid: int, authorization: str = Header(None)):
    need_auth(authorization)
    return {"text": tasks.complete_task(tid)}


@app.get("/api/canvas")
def api_canvas(authorization: str = Header(None)):
    need_auth(authorization)
    try:
        return {"text": canvas.canvas_upcoming(30)}
    except Exception as e:
        return {"text": f"erro: {e}"}


@app.get("/api/github")
def api_github(authorization: str = Header(None)):
    need_auth(authorization)
    try:
        return {"text": github.github_repos(15)}
    except Exception as e:
        return {"text": f"erro: {e}"}


@app.get("/api/outreach")
def api_outreach(authorization: str = Header(None)):
    need_auth(authorization)
    return {"items": leads.outreach_items("all")}


class Status(BaseModel):
    status: str


@app.post("/api/outreach/{lid}/status")
def api_outreach_status(lid: int, b: Status, authorization: str = Header(None)):
    need_auth(authorization)
    return {"text": leads.mark_outreach(lid, b.status)}


@app.get("/api/outreach/{lid}/link")
def api_outreach_link(lid: int, authorization: str = Header(None)):
    need_auth(authorization)
    return {"url": leads.whatsapp_link(lid)}


class Url(BaseModel):
    url: str


@app.post("/api/open")
def api_open(b: Url, authorization: str = Header(None)):
    """Abre um link no navegador padrão do Windows (só http/https)."""
    need_auth(authorization)
    if not re.match(r"^https?://", b.url):
        raise HTTPException(400, "só links http/https")
    webbrowser.open(b.url)
    return {"ok": True}


@app.get("/api/briefing")
async def api_briefing(authorization: str = Header(None)):
    need_auth(authorization)
    try:
        texto = await asyncio.get_running_loop().run_in_executor(pool, briefing.resumo, brain)
    except Exception as e:
        texto = f"Não consegui montar o resumo agora: {type(e).__name__}."
    return {"text": limpar(texto)}


@app.get("/api/jobs")
def api_jobs(authorization: str = Header(None)):
    need_auth(authorization)
    return {"items": jobs.job_items()}


@app.post("/api/jobs/{jid}/prepare")
async def api_job_prepare(jid: int, authorization: str = Header(None)):
    need_auth(authorization)
    return {"text": await asyncio.get_running_loop().run_in_executor(pool, jobs.prepare_application, jid)}


@app.get("/api/jobs/{jid}/application")
def api_job_app(jid: int, authorization: str = Header(None)):
    need_auth(authorization)
    return {"text": jobs.read_application(jid), "url": jobs.job_url(jid)}


@app.get("/api/reports")
def api_reports(authorization: str = Header(None)):
    need_auth(authorization)
    pasta = daily.REPORTS
    return sorted((p.name for p in pasta.glob("*.md")), reverse=True) if pasta.exists() else []


@app.get("/api/reports/{name}")
def api_report(name: str, authorization: str = Header(None)):
    need_auth(authorization)
    p = daily.REPORTS / Path(name).name
    return {"text": p.read_text(encoding="utf-8") if p.exists() else "(não encontrado)"}


@app.post("/api/daily")
async def api_daily(authorization: str = Header(None)):
    need_auth(authorization)
    arq = await asyncio.get_running_loop().run_in_executor(pool, daily.run)
    return {"file": arq.name}


# ---------- voz neural (Edge TTS) ----------
VOZES = {"pt-BR-FranciscaNeural", "pt-BR-ThalitaMultilingualNeural"}


class Fala(BaseModel):
    text: str
    voice: str = "pt-BR-FranciscaNeural"
    rate: str = "+8%"


@app.post("/api/tts")
async def api_tts(b: Fala, authorization: str = Header(None)):
    need_auth(authorization)
    voz = b.voice if b.voice in VOZES else "pt-BR-FranciscaNeural"
    rate = b.rate if b.rate.lstrip("+-").rstrip("%").isdigit() else "+8%"
    buf = bytearray()
    async for ch in edge_tts.Communicate(b.text[:1500], voz, rate=rate, pitch="+3Hz").stream():
        if ch["type"] == "audio":
            buf += ch["data"]
    if not buf:
        raise HTTPException(502, "sem áudio")
    return Response(bytes(buf), media_type="audio/mpeg")


# ---------- modo foco (disparado pelas palmas/estalos do sentinel.py) ----------
JANELAS = set()


@app.post("/api/foco")
async def api_foco(x_kyky: str = Header(None)):
    """Só o vigia chama (o cabeçalho próprio impede que outros sites disparem isso pelo navegador)."""
    if x_kyky != "sentinela":
        raise HTTPException(403, "só o vigia")
    for w in list(JANELAS):
        try:
            await w.send_json({"type": "focus"})
        except Exception:
            JANELAS.discard(w)
    return {"janelas": len(JANELAS)}


class Apps(BaseModel):
    apps: list[str]


@app.post("/api/foco/apps")
def api_foco_apps(b: Apps, authorization: str = Header(None)):
    """Abre os apps do modo foco (Spotify, VS Code...) pelo nome, como a ferramenta open_app."""
    need_auth(authorization)
    return {"resultado": [tools.execute("open_app", {"name": n}, lambda *a: False) for n in b.apps[:8] if n.strip()]}


# ---------- conversa por WebSocket ----------
@app.websocket("/ws")
async def ws_chat(ws: WebSocket, token: str = ""):
    if not auth.valid(token):
        await ws.close(code=4401)
        return
    await ws.accept()
    JANELAS.add(ws)
    loop = asyncio.get_running_loop()
    pending = {}
    busy = {"v": False}

    def send(obj):
        asyncio.run_coroutine_threadsafe(ws.send_json(obj), loop)

    def confirm(name, args):
        cid = uuid.uuid4().hex
        ev, box = threading.Event(), {"ok": False}
        pending[cid] = (ev, box)
        send({"type": "confirm", "id": cid, "text": tools.describe(name, args),
              "critical": name in tools.CRITICAL})
        ev.wait(180)
        pending.pop(cid, None)
        return box["ok"]

    def work(text, level):
        msgs = [{"role": "system", "content": sistema(level, text)}] + history[-20:] + [{"role": "user", "content": text}]
        try:
            answer, who = agent.run(brain, msgs, "code" if e_codigo(text) else level, confirm, max_steps=25 if e_codigo(text) else 10,
                                    specs=tools.subset() if e_codigo(text) else None,
                                    on_tool=lambda n, a: send({"type": "tool", "name": n}))
        except Exception as e:
            send({"type": "error", "text": str(e)[:300]})
            return
        answer = limpar(answer)
        history.extend([{"role": "user", "content": text}, {"role": "assistant", "content": answer}])
        memory.save("user", text)
        memory.save("assistant", answer, who)
        send({"type": "answer", "text": answer, "provider": who})

    async def run_chat(text, level):
        try:
            await loop.run_in_executor(pool, work, text, level)
        finally:
            busy["v"] = False
            await ws.send_json({"type": "idle"})

    try:
        while True:
            m = await ws.receive_json()
            if m.get("type") == "chat" and not busy["v"] and m.get("text", "").strip():
                busy["v"] = True
                asyncio.create_task(run_chat(m["text"].strip(), m.get("level", "strong")))
            elif m.get("type") == "auth" and m.get("id") in pending:
                ev, box = pending[m["id"]]
                crit = m.get("critical")
                if m.get("approve"):
                    if m.get("voice") and not crit:
                        try:
                            txt = await loop.run_in_executor(pool, transcrever, m["voice"]["audio"])
                            box["ok"] = auth.check_voice(txt, m["voice"]["vector"])
                        except Exception:
                            box["ok"] = False
                    else:
                        box["ok"] = auth.check_password(m.get("password", ""))
                    if not box["ok"]:
                        await ws.send_json({"type": "error", "text": "Autenticação recusada. Ação cancelada."})
                ev.set()
    except WebSocketDisconnect:
        for ev, _ in pending.values():
            ev.set()
    finally:
        JANELAS.discard(ws)


@app.get("/")
def index():
    return FileResponse(BASE / "web" / "index.html")


app.mount("/", StaticFiles(directory=BASE / "web"), name="web")

if __name__ == "__main__":
    import uvicorn
    (BASE / "data").mkdir(exist_ok=True)
    (BASE / "data" / "server.pid").write_text(str(os.getpid()))   # o start_kyky usa para reiniciar quando o código muda
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("KYKY_PORT", 8765)), log_level="warning", log_config=None)
