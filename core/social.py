"""Instagram somente leitura, pela sessão salva do navegador (python browser_login.py https://www.instagram.com).
A Kyky só LÊ o texto das páginas de atividade e mensagens. Não curte, segue, comenta nem envia nada.
Aviso: o Instagram não gosta de automação. Use com moderação (o resumo roda ao abrir o app, não em loop)."""
from . import browser

PAGINAS = (("Notificações", "https://www.instagram.com/accounts/activity/"),
           ("Mensagens", "https://www.instagram.com/direct/inbox/"))


def instagram_status():
    partes = []
    for nome, url in PAGINAS:
        txt = browser.read_page_logged(url)
        baixo = txt.lower()
        if ("esqueceu a senha" in baixo or "forgot password" in baixo) and ("entrar" in baixo or "log in" in baixo):
            return "sessão do Instagram não está logada (rode: python browser_login.py https://www.instagram.com)"
        partes.append(f"== {nome} ==\n{txt[:1500]}")
    return "\n\n".join(partes)
