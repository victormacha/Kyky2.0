"""Vagas: a Kyky busca, filtra e PREPARA a candidatura (carta + ajustes do currículo).
Ela não envia nada: você abre a vaga, revisa e confirma por conta própria.
Os fatos usados vêm só de candidate.md: preencha lá o seu currículo real."""
import re
import sqlite3
import time
from pathlib import Path
import requests
from . import vault, web
from .memory import DB

ROOT = Path(__file__).parent.parent
APPS = ROOT / "workspace" / "applications"
CANDIDATO = ROOT / "candidate.md"
SITES_VAGAS = ["gupy.io", "linkedin.com/jobs", "br.indeed.com", "vagas.com.br", "infojobs.com.br", "trampos.co", "catho.com.br"]


def _conn():
    c = sqlite3.connect(DB)
    c.execute("CREATE TABLE IF NOT EXISTS jobs(id INTEGER PRIMARY KEY, ts REAL, title TEXT, url TEXT UNIQUE, "
              "snippet TEXT, status TEXT DEFAULT 'nova', prepared TEXT)")
    return c


def search_jobs(query, location="", limit=8):
    """Busca vagas nos principais sites e guarda as novas na lista."""
    key = vault.get_key("tavily")
    if not key:
        return "erro: sem chave do Tavily"
    r = requests.post("https://api.tavily.com/search", timeout=40, json={
        "api_key": key, "query": f"vaga {query} {location}".strip(), "max_results": int(limit),
        "include_domains": SITES_VAGAS})
    r.raise_for_status()
    novas = []
    with _conn() as c:
        for x in r.json().get("results", []):
            cur = c.execute("INSERT OR IGNORE INTO jobs(ts,title,url,snippet) VALUES(?,?,?,?)",
                            (time.time(), x.get("title", "?")[:140], x["url"], (x.get("content") or "")[:500]))
            if cur.rowcount:
                novas.append(f"#{cur.lastrowid} {x.get('title', '?')[:90]}\n   {x['url']}")
    return ("Vagas novas:\n" + "\n".join(novas)) if novas else "nenhuma vaga nova encontrada"


def list_jobs(status="all"):
    q = "SELECT id,title,url,status FROM jobs" + ("" if status == "all" else " WHERE status=?") + " ORDER BY id DESC LIMIT 60"
    with _conn() as c:
        rows = c.execute(q, () if status == "all" else (status,)).fetchall()
    return "\n".join(f"#{i} [{st}] {t[:90]}\n   {u}" for i, t, u, st in rows) or "(nenhuma vaga salva)"


def job_items():
    with _conn() as c:
        rows = c.execute("SELECT id,title,url,snippet,status FROM jobs ORDER BY id DESC LIMIT 60").fetchall()
    return [dict(id=i, title=t, url=u, snippet=s, status=st) for i, t, u, s, st in rows]


def job_items():
    with _conn() as c:
        rows = c.execute("SELECT id,title,url,snippet,status FROM jobs ORDER BY id DESC LIMIT 60").fetchall()
    return [dict(id=i, title=t, url=u, snippet=s, status=st) for i, t, u, s, st in rows]


def job_items():
    with _conn() as c:
        rows = c.execute("SELECT id,title,url,snippet,status FROM jobs ORDER BY id DESC LIMIT 60").fetchall()
    return [dict(id=i, title=t, url=u, snippet=s, status=st) for i, t, u, s, st in rows]


def update_job(id, status):
    with _conn() as c:
        c.execute("UPDATE jobs SET status=? WHERE id=?", (status, int(id)))
    return f"vaga #{id} marcada como {status}"


def prepare_application(id, brain=None):
    """Gera carta de apresentação e ajustes de currículo para a vaga. Salva em workspace/applications/."""
    from .brain import Brain
    with _conn() as c:
        r = c.execute("SELECT title,url,snippet FROM jobs WHERE id=?", (int(id),)).fetchone()
    if not r:
        return "vaga não encontrada"
    title, url, snippet = r
    if not CANDIDATO.exists():
        return "erro: preencha o arquivo candidate.md com o seu currículo antes"
    try:
        pagina = web.fetch(url)
    except Exception:
        pagina = snippet
    perfil = CANDIDATO.read_text(encoding="utf-8")
    sistema = ("Você prepara candidaturas em português do Brasil. Use SOMENTE os fatos do perfil do candidato; "
               "nunca invente experiência, curso, tecnologia ou data. Se a vaga exige algo que o perfil não tem, "
               "diga isso com honestidade na seção de lacunas. Sem emojis.")
    pedido = (f"VAGA: {title}\nLINK: {url}\nTEXTO DA VAGA:\n{pagina[:6000]}\n\nPERFIL DO CANDIDATO:\n{perfil}\n\n"
              "Entregue em Markdown: 1) '## Compatibilidade' (nota de 0 a 10 e por quê, em 2 linhas); "
              "2) '## Carta de apresentação' (máx. 150 palavras, tom profissional e natural); "
              "3) '## Ajustes no currículo' (até 5 itens); 4) '## Lacunas' (o que a vaga pede e o perfil não mostra).")
    texto, _ = (brain or Brain()).ask([{"role": "system", "content": sistema}, {"role": "user", "content": pedido}], "strong")
    APPS.mkdir(parents=True, exist_ok=True)
    arq = APPS / f"vaga-{int(id)}.md"
    arq.write_text(f"# {title}\n{url}\n\n{texto}\n", encoding="utf-8")
    update_job(id, "preparada")
    with _conn() as c:
        c.execute("UPDATE jobs SET prepared=? WHERE id=?", (arq.name, int(id)))
    return f"candidatura preparada em workspace/applications/{arq.name} (revise e envie você mesmo)"


def read_application(id):
    p = APPS / f"vaga-{int(id)}.md"
    return p.read_text(encoding="utf-8") if p.exists() else "(ainda não preparada)"


def job_url(id):
    with _conn() as c:
        r = c.execute("SELECT url FROM jobs WHERE id=?", (int(id),)).fetchone()
    return r[0] if r else ""
