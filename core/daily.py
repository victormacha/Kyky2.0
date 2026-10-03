"""Rotina diária: lista do dia + pesquisas dos seus temas, salva em reports/AAAA-MM-DD.md."""
import json
from datetime import date
from pathlib import Path
from . import agent, tasks
from .brain import Brain

ROOT = Path(__file__).parent.parent
REPORTS = ROOT / "reports"
CONFIG = ROOT / "daily_config.json"
DEFAULT = {"topics": ["novidades em inteligência artificial"], "max_results": 4}


def _config():
    if not CONFIG.exists():
        CONFIG.write_text(json.dumps(DEFAULT, indent=2, ensure_ascii=False), encoding="utf-8")
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def run(brain=None, confirm=lambda n, a: False):
    """Gera o relatório do dia e devolve o caminho do arquivo."""
    brain = brain or Brain()
    cfg = _config()
    hoje = date.today().strftime("%d/%m/%Y")
    pedido = (
        f"Hoje é {hoje}. Monte meu relatório diário em português, em Markdown, com:\n"
        f"1. Seção 'Lista do dia': minhas tarefas pendentes (use list_tasks) e os prazos da faculdade (use canvas_upcoming; se der erro de configuração, apenas ignore), em ordem de prioridade, "
        f"com 1 linha de sugestão de como começar.\n"
        f"2. Seção 'Pesquisas': para cada tema abaixo, use web_search (até {cfg['max_results']} resultados) "
        f"e resuma o mais relevante e recente em 3 a 5 tópicos, citando os links.\n"
        f"Temas: {', '.join(cfg['topics'])}\n"
        "Use títulos Markdown (##) para as seções e ### para cada tema. Não invente fatos: só use o que as ferramentas devolverem. "
        "Não faça perguntas no final."
    )
    msgs = [{"role": "system", "content": "Você é a Kyky, assistente pessoal. Responda em português do Brasil."},
            {"role": "user", "content": pedido}]
    texto, who = agent.run(brain, msgs, "strong", confirm, max_steps=12)
    REPORTS.mkdir(exist_ok=True)
    arq = REPORTS / f"{date.today().isoformat()}.md"
    arq.write_text(f"# Relatório de {hoje}\n\n_gerado por {who}_\n\n{texto}\n", encoding="utf-8")
    return arq
