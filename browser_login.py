"""Abre o Edge com o perfil da Kyky para VOCÊ entrar nas suas contas (LinkedIn, GitHub, Gupy, Canvas...).
Faça o login normalmente, depois feche a janela. A sessão fica salva em data/browser_profile.
Uso:  python browser_login.py [url]"""
import sys
from playwright.sync_api import sync_playwright
from core.browser import PERFIL

url = sys.argv[1] if len(sys.argv) > 1 else "https://www.linkedin.com/login"
PERFIL.mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(str(PERFIL), channel="msedge", headless=False)
    pg = ctx.pages[0] if ctx.pages else ctx.new_page()
    pg.goto(url)
    print("Faça seu login na janela e depois FECHE a janela para salvar a sessão.")
    try:
        ctx.wait_for_event("close", timeout=0)
    except Exception:
        pass
