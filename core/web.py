"""Busca na web: Tavily primeiro (resultados limpos), DuckDuckGo como reserva.
Também baixa o texto de uma página."""
import re
import requests
from . import vault


def _tavily(query, n):
    key = vault.get_key("tavily")
    if not key:
        raise RuntimeError("sem chave tavily")
    r = requests.post("https://api.tavily.com/search", timeout=30, json={
        "api_key": key, "query": query, "max_results": n, "include_answer": True})
    r.raise_for_status()
    d = r.json()
    linhas = [f"Resposta resumida: {d['answer']}"] if d.get("answer") else []
    for x in d.get("results", []):
        linhas.append(f"- {x.get('title')}\n  {x.get('url')}\n  {(x.get('content') or '')[:400]}")
    return "\n".join(linhas) or "(sem resultados)"


def _ddg(query, n):
    from ddgs import DDGS
    res = DDGS().text(query, max_results=n)
    return "\n".join(f"- {x.get('title')}\n  {x.get('href')}\n  {(x.get('body') or '')[:400]}"
                     for x in res) or "(sem resultados)"


def search(query, max_results=5):
    erros = []
    for nome, fn in (("tavily", _tavily), ("duckduckgo", _ddg)):
        try:
            return f"[fonte: {nome}]\n" + fn(query, int(max_results))
        except Exception as e:
            erros.append(f"{nome}: {type(e).__name__} {str(e)[:80]}")
    return "erro: busca falhou\n" + "\n".join(erros)


def fetch(url):
    r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0 Kyky"})
    r.raise_for_status()
    t = re.sub(r"(?is)<(script|style).*?</\1>", " ", r.text)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t).strip()[:8000]
