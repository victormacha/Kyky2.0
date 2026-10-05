"""Resumo "como estão as minhas coisas": junta tarefas, Canvas, email e Instagram e devolve um texto curto para falar."""
from concurrent.futures import ThreadPoolExecutor

FONTES_PADRAO = ("tarefas", "canvas", "email", "instagram")
RECURSO = {"canvas": "canvas", "email": "email", "instagram": "instagram"}   # fonte -> recurso do dono.json


def coletar(fontes=FONTES_PADRAO):
    from . import canvas, dono, mail, social, tasks
    fontes = [f for f in fontes if f not in RECURSO or dono.tem(RECURSO[f])]
    mapa = {"tarefas": lambda: tasks.list_tasks("pending"), "canvas": lambda: canvas.canvas_upcoming(5),
            "email": lambda: mail.mail_unread(6), "instagram": social.instagram_status}
    saida = {}
    with ThreadPoolExecutor(4) as ex:
        futs = {n: ex.submit(mapa[n]) for n in fontes if n in mapa}
        for n, f in futs.items():
            try:
                saida[n] = f.result(timeout=60)
            except Exception as e:
                saida[n] = f"indisponível ({type(e).__name__}: {str(e)[:80]})"
    return saida


def resumo(brain=None):
    from .brain import Brain
    from .dono import NOME
    dados = coletar()
    bloco = "\n\n".join(f"### {k}\n{v}" for k, v in dados.items())
    pedido = (
        f"Com base APENAS nos dados abaixo, faça um resumo FALADO para {NOME}, em até 5 frases corridas, tom natural e direto. "
        "Priorize: prazos de hoje e amanhã, emails que parecem importantes (cite quem mandou e o assunto), mensagens e notificações novas. "
        "Se uma fonte estiver indisponível ou não configurada, diga isso numa frase curta e siga. Não invente nada. "
        "Sem listas, sem emojis, sem símbolos.\n\n" + bloco)
    texto, _ = (brain or Brain()).ask([
        {"role": "system", "content": f"Você é a Kyky, assistente pessoal de {NOME}. Português do Brasil."},
        {"role": "user", "content": pedido}], "fast")
    return texto
