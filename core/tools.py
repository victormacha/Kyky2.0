"""Ferramentas da Kyky. Caminho relativo = pasta 'workspace'; caminho absoluto (C:\\...) ou com ~ = qualquer lugar do PC.
Sobrescrever arquivo fora do workspace, abrir executáveis e rodar comandos pedem a sua confirmação."""
import os
import subprocess
import sys
from pathlib import Path
from . import web, tasks, leads, canvas, github, jobs, browser, mail, social, briefing, ponte

ROOT = Path(__file__).parent.parent
WORKSPACE = ROOT / "workspace"
WORKSPACE.mkdir(exist_ok=True)
HOME = Path.home()
PASTAS = {n: HOME / n for n in ("Desktop", "Documents", "Downloads", "Pictures", "Music", "Videos")}
EXECUTAVEIS = {".exe", ".bat", ".cmd", ".ps1", ".vbs", ".msi", ".lnk", ".js", ".jse", ".wsf", ".scr", ".com", ".py", ".pyw", ".reg"}

# auto = executa direto | ask = pede a sua confirmação antes (write_file e open_path decidem caso a caso)
PERMISSIONS = {"list_files": "auto", "read_file": "auto", "write_file": "auto", "run_python": "ask",
               "send_to_phone": "auto", "phone_files": "auto", "open_path": "auto", "open_app": "auto", "list_apps": "auto", "google_search": "auto", "run_command": "ask", "github_create_repo": "ask", "github_publish": "ask",
               "web_search": "auto", "fetch_url": "auto",
               "add_task": "auto", "list_tasks": "auto", "complete_task": "auto",
               "search_leads": "auto", "queue_outreach": "auto", "list_outreach": "auto",
               "whatsapp_link": "auto", "mark_outreach": "auto", "build_site": "auto",
               "canvas_courses": "auto", "canvas_upcoming": "auto",
               "github_repos": "auto", "github_status": "auto", "github_deploy": "ask", "anotar": "auto", "github_tree": "auto", "github_read": "auto", "github_search_code": "auto", "github_grep": "auto",
               "github_patch": "auto", "github_commit_patches": "ask",
               "search_jobs": "auto", "list_jobs": "auto", "update_job": "auto", "prepare_application": "auto",
               "read_page_logged": "auto",
               "mail_unread": "auto", "instagram_status": "auto", "briefing": "auto"}


NOTAS = []   # memória de trabalho do agente durante uma tarefa longa


def anotar(texto):
    """Guarda uma descoberta importante (ex: 'bug provável em ui.js:42, botão some no mobile')."""
    NOTAS.append(str(texto)[:400])
    return f"anotado ({len(NOTAS)} anotações)"


# ações críticas: só a senha aprova (a voz sozinha não basta)
CRITICAL = {"github_deploy", "github_publish"}


def _safe(rel):
    base = WORKSPACE.resolve()
    p = (base / rel).resolve()
    if p != base and base not in p.parents:
        raise ValueError("caminho fora da pasta de trabalho")
    return p


def _resolve(path):
    """Relativo -> dentro do workspace. Absoluto (C:\\...) ou ~ -> qualquer lugar do PC."""
    s = str(path or ".").strip().strip('"')
    if s.startswith("~"):
        return Path(s).expanduser().resolve()
    if Path(s).is_absolute():
        return Path(s).resolve()
    return _safe(s)


def _no_workspace(p):
    base = WORKSPACE.resolve()
    return p == base or base in p.parents


def list_files(path="."):
    base = _resolve(path)
    if not base.exists():
        return f"não existe: {base}"
    if _no_workspace(base):
        itens = sorted(str(p.relative_to(WORKSPACE)) for p in base.rglob("*") if p.is_file())
        return "\n".join(itens[:200]) or "(vazio)"
    # fora do workspace: só o conteúdo direto da pasta (pastas terminam com \)
    try:
        itens = sorted(base.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except PermissionError:
        return f"sem permissão para listar {base}"
    linhas = [p.name + ("\\" if p.is_dir() else "") for p in itens[:300]]
    mais = f"\n... e mais {len(itens) - 300}" if len(itens) > 300 else ""
    return f"{base}:\n" + ("\n".join(linhas) or "(vazia)") + mais


def read_file(path):
    return _resolve(path).read_text(encoding="utf-8", errors="replace")[:20000]


def write_file(path, content):
    p = _resolve(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"salvo: {p} ({len(content)} caracteres)"


def open_path(path):
    """Abre um arquivo no programa padrão, uma pasta no Explorer, ou um link no navegador."""
    s = str(path).strip().strip('"')
    if s.startswith(("http://", "https://")):
        os.startfile(s)
        return f"aberto no navegador: {s}"
    p = _resolve(s)
    if not p.exists():
        return f"não existe: {p}"
    os.startfile(str(p))
    return f"aberto: {p}"


_APPS = {"t": 0, "lista": []}
APELIDOS = {"navegador": "brave", "word": "word", "excel": "excel", "powerpoint": "powerpoint", "zap": "whatsapp",
            "bloco de notas": "bloco de notas", "notepad": "bloco de notas", "calculadora": "calculadora",
            "explorador": "explorador de arquivos", "vscode": "visual studio code", "vs code": "visual studio code"}


def _sem_acento(t):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", str(t).lower()) if unicodedata.category(c) != "Mn").strip()


def _apps():
    """Apps do Menu Iniciar (normais e da Microsoft Store), guardados por 10 minutos."""
    import json
    import time
    if time.time() - _APPS["t"] > 600 or not _APPS["lista"]:
        r = subprocess.run(["powershell", "-NoProfile", "-Command",
                            "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-StartApps | ConvertTo-Json -Compress"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        dados = json.loads(r.stdout or "[]")
        _APPS["lista"] = [(d["Name"], d["AppID"]) for d in (dados if isinstance(dados, list) else [dados])]
        _APPS["t"] = time.time()
    return _APPS["lista"]


def open_app(name):
    """Abre um aplicativo instalado pelo nome (Spotify, Discord, Word, Calculadora...)."""
    alvo = _sem_acento(APELIDOS.get(_sem_acento(name), name))
    apps = _apps()
    iguais = [a for a in apps if _sem_acento(a[0]) == alvo]
    comecam = [a for a in apps if _sem_acento(a[0]).startswith(alvo)]
    contem = [a for a in apps if alvo in _sem_acento(a[0])]
    achados = iguais or sorted(comecam, key=lambda a: len(a[0])) or sorted(contem, key=lambda a: len(a[0]))
    if not achados:
        return f"não achei nenhum app chamado '{name}' no Menu Iniciar"
    nome, appid = achados[0]
    subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{appid}"])
    outros = f" (também existem: {', '.join(a[0] for a in achados[1:5])})" if len(achados) > 1 else ""
    return f"abrindo {nome}{outros}"


def list_apps(filtro=""):
    f = _sem_acento(filtro)
    return "\n".join(sorted(n for n, _ in _apps() if f in _sem_acento(n))) or "nenhum app encontrado"


def google_search(query):
    """Abre a pesquisa no Google no navegador padrão do usuário (com a conta dele logada)."""
    from urllib.parse import quote_plus
    os.startfile("https://www.google.com/search?q=" + quote_plus(str(query)))
    return f"pesquisa aberta no navegador: {query}"


def run_command(command, cwd="", timeout=120):
    """Roda um comando no terminal do Windows (cmd). Sempre pede confirmação."""
    pasta = _resolve(cwd) if cwd else WORKSPACE
    try:
        r = subprocess.run(command, shell=True, cwd=pasta, capture_output=True, stdin=subprocess.DEVNULL,
                           text=True, encoding="utf-8", errors="replace", timeout=int(timeout))
    except subprocess.TimeoutExpired:
        return f"interrompido: passou de {timeout}s"
    out = (r.stdout or "") + (("\n[erros]\n" + r.stderr) if r.stderr else "")
    return f"código de saída {r.returncode}\n{out[-4000:]}"


def run_python(path, timeout=60):
    p = _resolve(path)
    try:
        r = subprocess.run([sys.executable, str(p)], cwd=p.parent, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=int(timeout))
    except subprocess.TimeoutExpired:
        return f"interrompido: passou de {timeout}s"
    out = (r.stdout or "") + (("\n[erros]\n" + r.stderr) if r.stderr else "")
    return f"código de saída {r.returncode}\n{out[:4000]}"


def needs_confirm(name, args):
    """Criar arquivo novo em qualquer lugar é livre; sobrescrever fora do workspace e abrir executável pedem confirmação."""
    try:
        if name == "write_file":
            p = _resolve(args.get("path", ""))
            return p.exists() and not _no_workspace(p)
        if name == "open_path":
            s = str(args.get("path", ""))
            return not s.startswith(("http://", "https://")) and _resolve(s).suffix.lower() in EXECUTAVEIS
    except Exception:
        return False
    return PERMISSIONS.get(name) == "ask"


FUNCS = {"list_files": list_files, "read_file": read_file, "write_file": write_file, "run_python": run_python,
         "send_to_phone": ponte.send_to_phone, "phone_files": ponte.phone_files, "open_path": open_path, "open_app": open_app, "list_apps": list_apps, "google_search": google_search, "run_command": run_command,
         "github_create_repo": github.github_create_repo, "github_publish": github.github_publish,
         "web_search": web.search, "fetch_url": web.fetch,
         "add_task": tasks.add_task, "list_tasks": tasks.list_tasks, "complete_task": tasks.complete_task,
         "search_leads": leads.search_leads, "queue_outreach": leads.queue_outreach, "list_outreach": leads.list_outreach,
         "whatsapp_link": leads.whatsapp_link, "mark_outreach": leads.mark_outreach, "build_site": leads.build_site,
         "canvas_courses": canvas.canvas_courses, "canvas_upcoming": canvas.canvas_upcoming,
         "github_repos": github.github_repos, "github_status": github.github_status, "github_deploy": github.github_deploy, "anotar": anotar, "github_tree": github.github_tree, "github_read": github.github_read, "github_search_code": github.github_grep, "github_grep": github.github_grep,
         "github_patch": github.github_patch, "github_commit_patches": github.github_commit_patches,
         "search_jobs": jobs.search_jobs, "list_jobs": jobs.list_jobs, "update_job": jobs.update_job,
         "prepare_application": jobs.prepare_application, "read_page_logged": browser.read_page_logged,
         "mail_unread": mail.mail_unread, "instagram_status": social.instagram_status, "briefing": briefing.resumo}


def _spec(name, desc, props, required):
    return {"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": required}}}


_s = {"type": "string"}
SPECS = [
    _spec("list_files", "Lista arquivos. Caminho relativo = workspace; caminho absoluto (ex: a pasta Desktop do usuário) = qualquer pasta do PC.",
          {"path": _s}, []),
    _spec("read_file", "Lê um arquivo de texto. Relativo = workspace; absoluto = qualquer lugar do PC.", {"path": _s}, ["path"]),
    _spec("write_file", "Cria ou sobrescreve um arquivo. Use caminho ABSOLUTO para salvar onde o usuário pediu "
          "(Área de Trabalho, Documentos...); relativo cai no workspace.", {"path": _s, "content": _s}, ["path", "content"]),
    _spec("open_path", "Abre no PC: arquivo no programa padrão, pasta no Explorer, ou link no navegador.",
          {"path": _s}, ["path"]),
    _spec("send_to_phone", "Manda um arquivo para o CELULAR do usuário: 'path' para um arquivo do PC que já existe, ou 'content' + 'name' "
          "para criar um arquivo novo (texto) direto no celular. 'nota' é um recado curto que aparece junto.",
          {"path": _s, "content": _s, "name": _s, "nota": _s}, []),
    _spec("phone_files", "Lista os arquivos que o celular mandou para o PC (ficam na pasta 'Do celular' da Área de Trabalho).",
          {"limit": {"type": "integer"}}, []),
    _spec("open_app", "Abre um aplicativo instalado no PC pelo nome (ex: Spotify, Discord, Word, Calculadora, Brave).",
          {"name": _s}, ["name"]),
    _spec("list_apps", "Lista os aplicativos instalados no PC (filtro opcional por nome).", {"filtro": _s}, []),
    _spec("google_search", "Abre uma pesquisa no Google no navegador do usuario, para ELE ver. Para voce mesma pesquisar e ler resultados, use web_search.",
          {"query": _s}, ["query"]),
    _spec("run_command", "Roda um comando no terminal do Windows (cmd), ex: git, pip, dir. Pede confirmação ao usuário.",
          {"command": _s, "cwd": _s, "timeout": {"type": "integer"}}, ["command"]),
    _spec("run_python", "Executa um script Python (relativo = workspace, ou caminho absoluto) e devolve a saída.",
          {"path": _s}, ["path"]),
    _spec("web_search", "Pesquisa na internet e devolve resultados com título, link e trecho.",
          {"query": _s, "max_results": {"type": "integer"}}, ["query"]),
    _spec("fetch_url", "Baixa o texto de uma página web a partir do link.", {"url": _s}, ["url"]),
    _spec("add_task", "Adiciona uma tarefa à lista do usuário (prazo opcional, formato AAAA-MM-DD).",
          {"text": _s, "due": _s}, ["text"]),
    _spec("list_tasks", "Lista as tarefas. status: 'pending' (padrão) ou 'all'.", {"status": _s}, []),
    _spec("complete_task", "Marca uma tarefa como concluída pelo id.", {"id": {"type": "integer"}}, ["id"]),
    _spec("search_leads", "Busca negócios locais sem site (leads) por nicho e cidade, com score de potencial.",
          {"niche": _s, "location": _s, "radius_km": {"type": "number"}, "min_score": {"type": "integer"},
           "limit": {"type": "integer"}}, ["niche", "location"]),
    _spec("queue_outreach", "Coloca um lead na fila de contato com mensagem pronta. NÃO envia nada; o usuário aprova e envia.",
          {"name": _s, "phone": _s, "address": _s, "score": {"type": "integer"},
           "style": {"type": "string", "enum": ["direto", "consultivo", "casual"]}, "site": _s}, ["name", "phone"]),
    _spec("list_outreach", "Lista a fila de contatos. status: pendente (padrão), enviado, all.", {"status": _s}, []),
    _spec("whatsapp_link", "Gera o link do WhatsApp com a mensagem pronta para um lead da fila.",
          {"id": {"type": "integer"}}, ["id"]),
    _spec("mark_outreach", "Atualiza o status de um lead da fila (ex: enviado, respondeu, descartado).",
          {"id": {"type": "integer"}, "status": _s}, ["id", "status"]),
    _spec("build_site", "Gera um mini-site de prévia (HTML) para um negócio, salvo em workspace/sites.",
          {"name": _s, "description": _s}, ["name", "description"]),
    _spec("canvas_courses", "Lista os cursos ativos do Canvas da faculdade.", {}, []),
    _spec("canvas_upcoming", "Lista tarefas do Canvas com prazo nos próximos dias e ainda não entregues.",
          {"days": {"type": "integer"}}, []),
    _spec("github_repos", "Lista os repositórios do GitHub do usuário.", {"limit": {"type": "integer"}}, []),
    _spec("github_status", "Mostra últimos commits e deploys (workflows) de um repositório 'dono/nome'.",
          {"repo": _s}, ["repo"]),
    _spec("github_deploy", "Dispara o deploy (workflow) de um repositório. Pede confirmação ao usuário.",
          {"repo": _s, "workflow": _s, "ref": _s}, ["repo"]),
    _spec("anotar", "Guarda na sua memória de trabalho uma descoberta importante (arquivo, linha, causa). Use para não precisar reler arquivos.",
          {"texto": _s}, ["texto"]),
    _spec("github_tree", "Lista todos os arquivos (inclusive em subpastas) de um repositório 'dono/nome'. Use SEMPRE antes de dizer que um repositório está vazio.",
          {"repo": _s, "path": _s}, ["repo"]),
    _spec("github_read", "Lê um arquivo de um repositório 'dono/nome' com números de linha. Para arquivos grandes use start e end (linhas) para ler só o trecho que importa.",
          {"repo": _s, "path": _s, "start": {"type": "integer"}, "end": {"type": "integer"}}, ["repo", "path"]),
    _spec("github_grep", "Procura um texto ou regex (ex: '@media|display: *none') em TODO o código do repositório e devolve arquivo:linha com contexto. É a melhor forma de achar onde algo está.",
          {"repo": _s, "pattern": _s, "context": {"type": "integer"}}, ["repo", "pattern"]),
    _spec("github_patch", "Prepara uma correção LOCAL num arquivo do repositório, trocando o trecho exato 'old' (aparece 1 vez) por 'new'. Não altera o GitHub.",
          {"repo": _s, "path": _s, "old": _s, "new": _s, "motivo": _s}, ["repo", "path", "old", "new"]),
    _spec("github_create_repo", "Cria um repositório novo (vazio) na conta GitHub do usuário. Pede confirmação.",
          {"name": _s, "private": {"type": "boolean"}, "description": _s}, ["name"]),
    _spec("github_publish", "Publica (git commit + push) uma pasta do PC num repositório do GitHub; cria o repositório se não existir. "
          "Recusa se houver chaves/senhas nos arquivos. Para se publicar, use a sua própria pasta. Pede a senha.",
          {"path": _s, "repo": _s, "mensagem": _s, "private": {"type": "boolean"}}, ["path", "repo"]),
    _spec("github_commit_patches", "Envia as correções salvas para um branch novo e abre um Pull Request. Pede confirmação do usuário.",
          {"repo": _s, "mensagem": _s}, ["repo"]),
    _spec("search_jobs", "Busca vagas de emprego/estágio nos principais sites e salva na lista.",
          {"query": _s, "location": _s, "limit": {"type": "integer"}}, ["query"]),
    _spec("list_jobs", "Lista as vagas salvas. status: all (padrão), nova, preparada, enviada, descartada.", {"status": _s}, []),
    _spec("update_job", "Atualiza o status de uma vaga (ex: enviada, descartada).",
          {"id": {"type": "integer"}, "status": _s}, ["id", "status"]),
    _spec("prepare_application", "Prepara carta de apresentação e ajustes de currículo para uma vaga. NÃO envia nada.",
          {"id": {"type": "integer"}}, ["id"]),
    _spec("read_page_logged", "Lê o texto de uma página usando a sessão de login salva do usuário (somente leitura).",
          {"url": _s}, ["url"]),
    _spec("mail_unread", "Mostra emails não lidos do Gmail (somente leitura: remetente, assunto, data).",
          {"limit": {"type": "integer"}}, []),
    _spec("instagram_status", "Lê notificações e mensagens novas do Instagram pela sessão salva (somente leitura).", {}, []),
    _spec("briefing", "Resumo de como estão as coisas do usuário: tarefas, Canvas, email e Instagram.", {}, []),
]


GRUPOS = {"github": lambda n: n.startswith("github_"),
          "leads": lambda n: n in ("search_leads", "queue_outreach", "list_outreach", "whatsapp_link", "mark_outreach", "build_site"),
          "vagas": lambda n: n in ("search_jobs", "list_jobs", "update_job", "prepare_application"),
          "canvas": lambda n: n.startswith("canvas_"),
          "email": lambda n: n == "mail_unread",
          "instagram": lambda n: n in ("instagram_status", "read_page_logged")}


def _ligada(nome):
    from . import dono
    return all(dono.tem(g) or not teste(nome) for g, teste in GRUPOS.items())


SPECS = [s for s in SPECS if _ligada(s["function"]["name"])]


def subset(prefixos=("github_", "anotar", "list_files", "read_file", "write_file", "open_path", "open_app", "run_command", "send_to_phone", "phone_files")):
    """Só as ferramentas relevantes (economiza tokens em tarefas de código)."""
    return [s for s in SPECS if s["function"]["name"].startswith(tuple(prefixos))]


def describe(name, args):
    """Texto mostrado ao usuário antes de pedir permissão."""
    if name == "github_commit_patches":
        base = github.PATCHES / github._slug(args.get("repo", ""))
        arqs = [p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file() and p.name != "RESUMO.md"] if base.exists() else []
        return (f"abrir Pull Request em {args.get('repo')} com a mensagem '{args.get('mensagem', 'Correção sugerida pela Kyky')}'\n"
                "arquivos alterados:\n  " + "\n  ".join(arqs or ["(nenhum)"]))
    if name == "run_command":
        return f"rodar no terminal (em {args.get('cwd') or WORKSPACE}):\n    > {args.get('command')}"
    if name == "write_file":
        return f"SOBRESCREVER o arquivo existente {_resolve(args.get('path', ''))}"
    if name == "open_path":
        return f"abrir/executar o programa {_resolve(args.get('path', ''))}"
    if name == "github_publish":
        return (f"publicar a pasta {_resolve(args.get('path', ''))}\nno GitHub em {args.get('repo')} "
                f"({'privado' if github._verdade(args.get('private')) else 'PÚBLICO'} se for criado agora)\n"
                f"mensagem: {args.get('mensagem') or 'Atualização pela Kyky'}")
    if name == "run_python":
        try:
            linhas = read_file(args.get("path", "")).splitlines()
            prev = "\n".join("    | " + l for l in linhas[:40])
            extra = f"\n    | ... (+{len(linhas) - 40} linhas)" if len(linhas) > 40 else ""
            return f"rodar {args.get('path')}:\n{prev}{extra}"
        except Exception:
            pass
    return f"{name} {args}"


def execute(name, args, confirm):
    fn = FUNCS.get(name) if _ligada(name) else None
    if not fn:
        return f"erro: ferramenta desconhecida ({name})"
    try:
        if needs_confirm(name, args) and not confirm(name, args):
            return "negado pelo usuário"
        out = str(fn(**args))
        return out if len(out) <= 9000 else out[:9000] + "\n[... resultado cortado: use start/end ou um padrão mais específico]"
    except Exception as e:
        return f"erro: {type(e).__name__}: {e}"
