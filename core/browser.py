"""Navegador com sessão salva: VOCÊ faz login uma vez (python browser_login.py) e a Kyky reaproveita o
perfil para LER páginas que exigem conta. Ela nunca digita a sua senha e aqui não clica nem envia nada."""
from pathlib import Path

PERFIL = Path(__file__).parent.parent / "data" / "browser_profile"


def read_page_logged(url):
    """Abre a página com a sua sessão salva (Edge, sem janela) e devolve o texto visível."""
    from playwright.sync_api import sync_playwright
    PERFIL.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(str(PERFIL), channel="msedge", headless=True)
        try:
            pg = ctx.new_page()
            pg.goto(url, timeout=45000, wait_until="domcontentloaded")
            pg.wait_for_timeout(2500)
            return pg.inner_text("body")[:8000]
        finally:
            ctx.close()
