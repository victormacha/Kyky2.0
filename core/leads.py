"""Nexus dentro da Kyky: busca de leads (TomTom), site de prévia e fila de contato.
A Kyky NUNCA envia mensagem sozinha: ela prepara, você aprova e clica no link."""
import json
import math
import re
import sqlite3
import time
from datetime import date
from pathlib import Path
from urllib.parse import quote
import requests
from . import vault
from .memory import DB

SITES = Path(__file__).parent.parent / "workspace" / "sites"
ESTILOS = {
    "direto": "Olá! Vi o perfil da {n} e notei que vocês ainda não têm um site oficial para receber pedidos/agendamentos. Criei uma prévia de como ficaria a estrutura de vocês. Posso te enviar por aqui sem compromisso?",
    "consultivo": "Oi, tudo bem? Trabalho ajudando negócios locais a converter mais clientes online e reparei que a {n} ainda não tem um site próprio. Isso costuma custar agendamentos/pedidos que iam pra concorrência com site. Faz sentido eu te mostrar uma prévia gratuita de como ficaria?",
    "casual": "Opa! Passando aqui rapidinho — vi a {n} e achei o trabalho de vocês muito bom 👏 Só senti falta de um site pra facilitar a vida de quem procura vocês no Google. Já fiz uma prévia rapidinha, quer dar uma olhada?",
}


def _conn():
    c = sqlite3.connect(DB)
    c.execute("CREATE TABLE IF NOT EXISTS outreach(id INTEGER PRIMARY KEY, ts REAL, name TEXT, address TEXT, "
              "phone TEXT, score INTEGER, message TEXT, site TEXT, status TEXT DEFAULT 'pendente')")
    return c


def _km(a, b, c, d):
    p = math.pi / 180
    x = math.sin((c - a) * p / 2) ** 2 + math.cos(a * p) * math.cos(c * p) * math.sin((d - b) * p / 2) ** 2
    return 12742 * math.asin(math.sqrt(x))


def _score(has_site, phone, hours, open_now, dist):
    prox = 5 if dist is not None and dist <= 3 else 2 if dist is not None and dist <= 8 else 0
    if has_site:
        return min(15 + (10 if phone else 0) + (5 if open_now else 0) + prox, 40)
    return min(45 + (20 if phone else 0) + (12 if hours else 0) + (13 if open_now else 0) + prox, 100)


def search_leads(niche, location, radius_km=10, min_score=60, limit=10):
    key = vault.get_key("tomtom")
    if not key:
        return "erro: sem chave da TomTom"
    g = requests.get(f"https://api.tomtom.com/search/2/geocode/{quote(location)}.json",
                     params={"key": key, "countrySet": "BR", "limit": 1}, timeout=20).json()
    if not g.get("results"):
        return "erro: cidade não encontrada"
    c = g["results"][0]["position"]
    r = requests.get(f"https://api.tomtom.com/search/2/poiSearch/{quote(niche)}.json", timeout=20, params={
        "key": key, "limit": 100, "countrySet": "BR", "lat": c["lat"], "lon": c["lon"],
        "radius": int(float(radius_km) * 1000), "openingHours": "nextSevenDays"})
    r.raise_for_status()
    hoje, agora, leads = date.today().isoformat(), time.strftime("%Y-%m-%dT%H:%M"), []
    for x in r.json().get("results", []):
        poi, pos = x.get("poi", {}), x.get("position", {})
        phone = re.sub(r"\D", "", poi.get("phone") or "")
        trs = (poi.get("openingHours") or {}).get("timeRanges") or []
        hours = [t for t in trs if t["startTime"]["date"] == hoje]
        fmt = lambda t: f"{t['date']}T{t['hour']:02d}:{t['minute']:02d}"
        open_now = any(fmt(t["startTime"]) <= agora <= fmt(t["endTime"]) for t in trs) if trs else None
        dist = _km(c["lat"], c["lon"], pos["lat"], pos["lon"]) if pos else None
        s = _score(bool(poi.get("url")), phone, bool(trs), open_now, dist)
        if s >= int(min_score) and phone:
            leads.append({"name": poi.get("name", "?"), "address": (x.get("address") or {}).get("freeformAddress", ""),
                          "phone": phone, "score": s, "open_now": open_now, "dist": dist})
    leads.sort(key=lambda l: -l["score"])
    leads = leads[:int(limit)]
    if not leads:
        return "nenhum lead com esses critérios"
    novos = 0
    with _conn() as c:
        ja = {r[0] for r in c.execute("SELECT phone FROM outreach")}
    for l in leads:
        if l["phone"] not in ja:
            queue_outreach(l["name"], l["phone"], l["address"], l["score"], "direto")
            novos += 1
    resumo = "; ".join(f"{l['name']} (nota {l['score']})" for l in leads[:5])
    return (f"{len(leads)} leads encontrados, {novos} novos já estão na aba Leads, prontos para você abrir o WhatsApp. "
            f"Melhores: {resumo}")


def queue_outreach(name, phone, address="", score=0, style="direto", site=""):
    """Põe um lead na fila. Mensagem pronta; nada é enviado."""
    msg = ESTILOS.get(style, ESTILOS["direto"]).format(n=name)
    with _conn() as c:
        cur = c.execute("INSERT INTO outreach(ts,name,address,phone,score,message,site) VALUES(?,?,?,?,?,?,?)",
                        (time.time(), name, address, re.sub(r"\D", "", phone), int(score), msg, site))
    return f"lead #{cur.lastrowid} ({name}) na fila, aguardando sua aprovação"


def list_outreach(status="pendente"):
    q = "SELECT id,name,phone,score,status,site FROM outreach" + ("" if status == "all" else " WHERE status=?")
    with _conn() as c:
        rows = c.execute(q, () if status == "all" else (status,)).fetchall()
    return "\n".join(f"#{i} {n} | {p} | score {s} | {st}" + (f" | site: {site}" if site else "")
                     for i, n, p, s, st, site in rows) or "(fila vazia)"


def outreach_items(status="all"):
    q = "SELECT id,name,address,phone,score,status,site FROM outreach" + ("" if status == "all" else " WHERE status=?") + " ORDER BY (status='pendente') DESC, score DESC, id DESC"
    with _conn() as c:
        rows = c.execute(q, () if status == "all" else (status,)).fetchall()
    return [dict(id=i, name=n, address=a, phone=p, score=s, status=st, site=si) for i, n, a, p, s, st, si in rows]


def outreach_items(status="all"):
    q = "SELECT id,name,address,phone,score,status,site FROM outreach" + ("" if status == "all" else " WHERE status=?") + " ORDER BY (status='pendente') DESC, score DESC, id DESC"
    with _conn() as c:
        rows = c.execute(q, () if status == "all" else (status,)).fetchall()
    return [dict(id=i, name=n, address=a, phone=p, score=s, status=st, site=si) for i, n, a, p, s, st, si in rows]


def outreach_items(status="all"):
    q = "SELECT id,name,address,phone,score,status,site FROM outreach" + ("" if status == "all" else " WHERE status=?") + " ORDER BY (status='pendente') DESC, score DESC, id DESC"
    with _conn() as c:
        rows = c.execute(q, () if status == "all" else (status,)).fetchall()
    return [dict(id=i, name=n, address=a, phone=p, score=s, status=st, site=si) for i, n, a, p, s, st, si in rows]


def whatsapp_link(id):
    """Link wa.me com a mensagem pronta. Quem clica em enviar é você."""
    with _conn() as c:
        r = c.execute("SELECT phone, message FROM outreach WHERE id=?", (int(id),)).fetchone()
    if not r:
        return "lead não encontrado"
    ph = r[0] if (r[0].startswith("55") and len(r[0]) >= 12) else "55" + r[0]
    return f"https://wa.me/{ph}?text={quote(r[1])}"


def mark_outreach(id, status):
    with _conn() as c:
        c.execute("UPDATE outreach SET status=? WHERE id=?", (status, int(id)))
    return f"lead #{id} marcado como {status}"


def build_site(name, description, brain=None):
    """Gera um mini-site de prévia (HTML) em workspace/sites/ usando a IA da Kyky + fotos do Pexels."""
    from .brain import Brain
    brain = brain or Brain()
    sistema = ("Você cria textos para mini-sites de prévia de pequenos negócios brasileiros. Responda APENAS com JSON: "
               '{"headline":"","subheadline":"","sobreNos":"","servicos":["","","",""],"cta":"","imageQuery":"2-4 palavras em inglês"}. '
               "Nunca invente telefone, endereço ou preço.")
    txt, _ = brain.ask([{"role": "system", "content": sistema},
                        {"role": "user", "content": f"Negócio: {name}\n{description}"}], "strong")
    d = json.loads(re.search(r"\{.*\}", txt, re.S).group(0))
    fotos = []
    if vault.get_key("pexels"):
        try:
            j = requests.get("https://api.pexels.com/v1/search", timeout=20, headers={"Authorization": vault.get_key("pexels")},
                             params={"query": d.get("imageQuery", "small business"), "per_page": 4, "orientation": "landscape"}).json()
            fotos = [p["src"]["large"] for p in j.get("photos", [])]
        except Exception:
            pass
    esc = lambda s: str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    hero = fotos[0] if fotos else ""
    galeria = "".join(f'<img src="{u}" alt="">' for u in fotos[1:4])
    html = (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{esc(name)}</title><style>body{{margin:0;font-family:system-ui,sans-serif;background:#0f172a;color:#f1f5f9}}'
            f'.hero{{background:linear-gradient(rgba(9,13,22,.75),rgba(9,13,22,.85)),url({hero}) center/cover;padding:90px 24px;text-align:center}}'
            f'.hero p{{max-width:560px;margin:12px auto 24px;color:#cbd5e1}}.cta{{background:#39ff88;color:#090d16;padding:14px 28px;border-radius:12px;font-weight:800;text-decoration:none}}'
            f'.s{{max-width:900px;margin:0 auto;padding:48px 24px}}.s p{{color:#cbd5e1;line-height:1.7}}.g{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}.g img{{width:100%;height:140px;object-fit:cover;border-radius:12px}}'
            f'ul{{list-style:none;padding:0;display:grid;gap:10px}}li{{background:#141b2d;border-radius:10px;padding:14px 18px}}</style></head><body>'
            f'<div class="hero"><h1>{esc(d["headline"])}</h1><p>{esc(d["subheadline"])}</p><a class="cta" href="#">{esc(d["cta"])}</a></div>'
            f'<div class="s"><h2>Sobre nós</h2><p>{esc(d["sobreNos"])}</p><div class="g">{galeria}</div></div>'
            f'<div class="s"><h2>Serviços</h2><ul>{"".join(f"<li>✓ {esc(x)}</li>" for x in d["servicos"])}</ul></div></body></html>')
    SITES.mkdir(parents=True, exist_ok=True)
    arq = SITES / (re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") + ".html")
    arq.write_text(html, encoding="utf-8")
    return f"site salvo em {arq.relative_to(SITES.parent)}"
