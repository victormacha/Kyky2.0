"""GitHub pela API oficial. Precisa de 'github_token' (GitHub > Settings > Developer settings >
Personal access tokens, com escopos 'repo' e 'workflow') no cofre ou em secrets_local.py.
Leitura é livre; o deploy (dispara um workflow) sempre pede a sua confirmação."""
import requests
from . import vault

API = "https://api.github.com"


def _h():
    tok = vault.get_key("github_token")
    if not tok:
        raise RuntimeError("configure 'github_token' (veja core/github.py)")
    return {"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"}


def _get(path, **params):
    r = requests.get(f"{API}/{path}", headers=_h(), params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def github_repos(limit=30):
    rs = _get("user/repos", sort="pushed", per_page=int(limit))
    return "\n".join(f"{r['full_name']} | {'privado' if r['private'] else 'público'} | push {r['pushed_at'][:10]}"
                     for r in rs) or "(sem repositórios)"


def github_status(repo):
    """Últimos commits e execuções de workflow (deploys) de um repositório 'dono/nome'."""
    cs = _get(f"repos/{repo}/commits", per_page=5)
    ws = _get(f"repos/{repo}/actions/runs", per_page=5).get("workflow_runs", [])
    out = ["Commits:"] + [f"- {c['sha'][:7]} {c['commit']['message'].splitlines()[0]}" for c in cs]
    out += ["Workflows:"] + [f"- {w['name']} | {w['status']}/{w.get('conclusion')} | {w['created_at'][:16]}" for w in ws]
    return "\n".join(out)


def github_deploy(repo, workflow="deploy.yml", ref="main"):
    """Dispara o workflow de deploy (workflow_dispatch). Exige confirmação em tools.PERMISSIONS."""
    r = requests.post(f"{API}/repos/{repo}/actions/workflows/{workflow}/dispatches",
                      headers=_h(), json={"ref": ref}, timeout=30)
    if r.status_code != 204:
        return f"erro {r.status_code}: {r.text[:200]}"
    return f"deploy disparado: {repo} ({workflow} em {ref})"


def github_tree(repo, path=""):
    """Lista TODOS os arquivos do repositório (inclui subpastas). Use antes de dizer que um repositório está vazio."""
    info = _get(f"repos/{repo}")
    t = _get(f"repos/{repo}/git/trees/{info['default_branch']}", recursive=1)
    itens = [x for x in t.get("tree", []) if x["type"] == "blob" and x["path"].startswith(path)]
    if not itens:
        return f"nenhum arquivo em '{path or '/'}' (branch {info['default_branch']}, {info['size']} KB)"
    linhas = [f"{x['path']} ({x.get('size', 0)} B)" for x in itens[:150]]
    mais = f"\n... e mais {len(itens) - 150} arquivos" if len(itens) > 150 else ""
    return f"branch {info['default_branch']}, {len(itens)} arquivos:\n" + "\n".join(linhas) + mais


_CACHE = {}
EXTS = (".js", ".ts", ".css", ".html", ".json", ".md", ".sql", ".py", ".toml", ".yml", ".yaml", ".txt", ".jsx", ".tsx", ".vue")


def _arquivos(repo):
    """Baixa (e guarda por 10 minutos) o texto de todos os arquivos de código do repositório."""
    c = _CACHE.get(repo)
    if c and time.time() - c[0] < 600:
        return c[1]
    import base64
    info = _get(f"repos/{repo}")
    arvore = _get(f"repos/{repo}/git/trees/{info['default_branch']}", recursive=1)["tree"]
    alvo = [x for x in arvore if x["type"] == "blob" and x["path"].lower().endswith(EXTS) and x.get("size", 0) < 250_000][:80]
    from concurrent.futures import ThreadPoolExecutor

    def baixa(x):
        try:
            d = _get(f"repos/{repo}/contents/{x['path']}")
            return x["path"], base64.b64decode(d["content"]).decode("utf-8", "replace")
        except Exception:
            return x["path"], ""
    with ThreadPoolExecutor(8) as ex:
        arqs = dict(ex.map(baixa, alvo))
    _CACHE[repo] = (time.time(), arqs)
    return arqs


def github_grep(repo, pattern, context=2):
    """Procura um texto ou regex em TODO o código do repositório. Devolve arquivo:linha com contexto."""
    import re
    try:
        rx = re.compile(pattern, re.I)
    except re.error:
        rx = re.compile(re.escape(pattern), re.I)
    saida, total = [], 0
    for path, txt in _arquivos(repo).items():
        linhas = txt.splitlines()
        for n, l in enumerate(linhas):
            if rx.search(l):
                total += 1
                if len(saida) < 45:
                    a, b = max(0, n - int(context)), min(len(linhas), n + int(context) + 1)
                    saida.append(f"{path}:{n + 1}\n" + "\n".join(f"  {k + 1}| {linhas[k][:160]}" for k in range(a, b)))
    if not saida:
        return "nenhuma ocorrência"
    return f"{total} ocorrências (mostrando {len(saida)}):\n" + "\n".join(saida)


def github_read(repo, path, start=1, end=0):
    """Lê um arquivo do repositório com números de linha. Use start e end para ler só um trecho."""
    txt = _arquivos(repo).get(path)
    if txt is None:
        txt, _ = _remote(repo, path)
    linhas = txt.splitlines()
    a = max(1, int(start))
    b = int(end) if int(end) > 0 else len(linhas)
    corpo = "\n".join(f"{n}| {linhas[n - 1]}" for n in range(a, min(b, len(linhas)) + 1))
    cab = f"{path} ({len(linhas)} linhas), mostrando {a}-{min(b, len(linhas))}\n"
    return cab + (corpo if len(corpo) <= 16000 else corpo[:16000] + "\n[... cortado: peça um trecho menor com start e end]")


# ---------------------------------------------------------------- correção de código
import difflib
import time
from pathlib import Path

PATCHES = Path(__file__).parent.parent / "workspace" / "patches"


def _slug(repo):
    return repo.replace("/", "__")


def _remote(repo, path):
    import base64
    d = _get(f"repos/{repo}/contents/{path}")
    return base64.b64decode(d["content"]).decode("utf-8", "replace"), d["sha"]


def github_search_code(repo, query):
    return github_grep(repo, query)


def _search_code_api(repo, query):
    """Procura um termo no código do repositório e devolve os arquivos onde aparece."""
    r = requests.get(f"{API}/search/code", headers=_h(), params={"q": f"{query} repo:{repo}", "per_page": 15}, timeout=30)
    if r.status_code != 200:
        return f"busca indisponível ({r.status_code}); use github_tree e github_read"
    itens = r.json().get("items", [])
    return "\n".join(x["path"] for x in itens) or "nenhum arquivo contém esse termo"


def github_patch(repo, path, old, new, motivo=""):
    """Prepara uma correção LOCAL (não mexe no GitHub): troca o trecho exato 'old' por 'new' no arquivo."""
    local = PATCHES / _slug(repo) / path
    original, _ = _remote(repo, path)
    atual = local.read_text(encoding="utf-8", newline="") if local.exists() else original
    if "\r\n" in atual and "\r\n" not in old:
        old, new = old.replace("\n", "\r\n"), new.replace("\n", "\r\n")
    n = atual.count(old)
    if n != 1:
        return f"erro: o trecho 'old' aparece {n} vezes (precisa aparecer exatamente 1). Use um trecho maior e único, copiado do arquivo."
    novo = atual.replace(old, new, 1)
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text(novo, encoding="utf-8", newline="")
    diff = "".join(difflib.unified_diff(original.splitlines(True), novo.splitlines(True), f"a/{path}", f"b/{path}", n=2))
    resumo = PATCHES / _slug(repo) / "RESUMO.md"
    with open(resumo, "a", encoding="utf-8") as f:
        f.write(f"\n## {path}\n{motivo}\n```diff\n{diff[:4000]}\n```\n")
    return f"correção salva localmente em workspace/patches/{_slug(repo)}/{path}\n{diff[:2500]}"


def github_commit_patches(repo, mensagem="Correção sugerida pela Kyky"):
    """Cria um branch, envia os arquivos corrigidos e abre um Pull Request. Exige confirmação do usuário."""
    import base64
    base = PATCHES / _slug(repo)
    arquivos = [p for p in base.rglob("*") if p.is_file() and p.name != "RESUMO.md"] if base.exists() else []
    if not arquivos:
        return "nenhuma correção salva para enviar (use github_patch antes)"
    padrao = _get(f"repos/{repo}")["default_branch"]
    sha_base = _get(f"repos/{repo}/git/ref/heads/{padrao}")["object"]["sha"]
    branch = f"kyky/fix-{time.strftime('%Y%m%d-%H%M')}"
    r = requests.post(f"{API}/repos/{repo}/git/refs", headers=_h(), json={"ref": f"refs/heads/{branch}", "sha": sha_base}, timeout=30)
    if r.status_code >= 300:
        return f"erro {r.status_code} ao criar o branch: o token precisa de 'Contents: Read and write'. {r.text[:150]}"
    for f in arquivos:
        rel = f.relative_to(base).as_posix()
        _, sha = _remote(repo, rel)
        r = requests.put(f"{API}/repos/{repo}/contents/{rel}", headers=_h(), timeout=30, json={
            "message": mensagem, "branch": branch, "sha": sha,
            "content": base64.b64encode(f.read_bytes()).decode()})
        if r.status_code >= 300:
            return f"erro {r.status_code} ao enviar {rel}: {r.text[:150]}"
    corpo = (base / "RESUMO.md").read_text(encoding="utf-8")[:6000] if (base / "RESUMO.md").exists() else ""
    r = requests.post(f"{API}/repos/{repo}/pulls", headers=_h(), timeout=30,
                      json={"title": mensagem, "head": branch, "base": padrao, "body": corpo + "\n\nPreparado pela Kyky. Revise antes de aprovar."})
    if r.status_code >= 300:
        return f"branch {branch} criado e arquivos enviados, mas o Pull Request falhou ({r.status_code}): {r.text[:150]}"
    return f"Pull Request aberto: {r.json()['html_url']}"


# ---------------------------------------------------------------- criar e publicar repositórios
import base64 as _b64
import os
import re
import subprocess

DICA_TOKEN = ("o token do GitHub não tem permissão. Em github.com > Settings > Developer settings > Fine-grained tokens, "
              "edite o token: Repository access = All repositories; Permissions > Administration = Read and write "
              "e Contents = Read and write. Depois salve de novo em 'github_token'.")
# nunca publicar: sessões do navegador, senhas, bancos locais, chaves
PROIBIDOS = re.compile(r"(^|/)(secrets_local\.py|keys\.txt|auth\.json|\.env(\..*)?|.*\.db|.*\.pem|id_rsa.*|Cookies|Login Data)$"
                       r"|(^|/)browser_profile/", re.I)
SEGREDOS = r"github_pat_[A-Za-z0-9_]{20,}|ghp_[A-Za-z0-9]{30,}|sk-or-v1-[a-f0-9]{20,}|gsk_[A-Za-z0-9]{20,}|tvly-[A-Za-z0-9-]{20,}|AIza[A-Za-z0-9_-]{30,}|sk-[A-Za-z0-9]{32,}"


def _verdade(v, padrao=True):
    if v is None or v == "":
        return padrao
    return str(v).strip().lower() not in ("false", "0", "no", "nao", "não", "publico", "público", "public")


def _nome_completo(repo):
    repo = repo.strip().strip("/").removeprefix("https://github.com/").removesuffix(".git")
    return repo if "/" in repo else f"{_get('user')['login']}/{repo}"


def github_create_repo(name, private=True, description=""):
    """Cria um repositório vazio na conta do usuário."""
    nome = name.split("/")[-1].strip()
    r = requests.post(f"{API}/user/repos", headers=_h(), timeout=30,
                      json={"name": nome, "private": _verdade(private), "description": description or ""})
    if r.status_code == 201:
        d = r.json()
        return f"repositório criado: {d['html_url']} ({'privado' if d['private'] else 'público'})"
    if r.status_code == 422 and "already exists" in r.text:
        return f"já existe um repositório '{nome}' na sua conta"
    if r.status_code in (401, 403, 404):
        return f"erro {r.status_code}: {DICA_TOKEN}"
    return f"erro {r.status_code}: {r.text[:200]}"


def _git(args, pasta, env=None):
    r = subprocess.run(["git", *args], cwd=pasta, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", stdin=subprocess.DEVNULL, env=env, timeout=300)
    return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()


def github_publish(path, repo, mensagem="Atualização pela Kyky", private=True):
    """git add + commit + push de uma pasta local para github.com/repo (cria o repositório se não existir)."""
    from .tools import _resolve
    if not (str(path).strip().startswith("~") or Path(str(path).strip().strip('"')).is_absolute()):
        return "erro: informe o caminho ABSOLUTO da pasta a publicar (ex: a sua própria pasta, indicada no seu sistema)"
    pasta = _resolve(path)
    if not pasta.is_dir():
        return f"pasta não encontrada: {pasta}"
    repo = _nome_completo(repo)
    r = requests.get(f"{API}/repos/{repo}", headers=_h(), timeout=30)
    if r.status_code == 404:
        dono, nome = repo.split("/", 1)
        if dono.lower() != _get("user")["login"].lower():
            return f"o repositório {repo} não existe e só consigo criar na sua própria conta"
        criado = github_create_repo(nome, private)
        if not criado.startswith("repositório criado"):
            return criado
    elif r.status_code >= 300:
        return f"erro {r.status_code} ao acessar {repo}: {DICA_TOKEN if r.status_code in (401, 403) else r.text[:150]}"

    if not (pasta / ".git").exists():
        cod, out = _git(["init", "-b", "main"], pasta)
        if cod:
            return f"erro no git init: {out[:300]}"
    _git(["add", "-A"], pasta)
    _, lista = _git(["diff", "--cached", "--name-only"], pasta)
    _, todos = _git(["ls-files"], pasta)
    ruins = [f for f in set(todos.splitlines()) | set(lista.splitlines()) if PROIBIDOS.search(f)]
    _, vazou = _git(["grep", "--cached", "-l", "-I", "-E", SEGREDOS], pasta)
    ruins += [f for f in vazou.splitlines() if f.strip()]
    if ruins:
        return ("CANCELADO: estes arquivos têm chaves, senhas ou sessões e não podem ir para o GitHub. "
                "Coloque-os no .gitignore e rode 'git rm --cached' neles:\n  " + "\n  ".join(sorted(set(ruins))[:30]))

    login = _get("user")["login"]
    cfg = []
    if _git(["config", "user.email"], pasta)[0]:
        cfg = ["-c", f"user.name={login}", "-c", f"user.email={login}@users.noreply.github.com"]
    commit = "nada novo para commitar"
    if lista.strip():
        cod, out = _git([*cfg, "commit", "-m", mensagem or "Atualização pela Kyky"], pasta)
        if cod:
            return f"erro no commit: {out[:300]}"
        commit = f"{len(lista.splitlines())} arquivo(s) commitado(s)"
    if _git(["remote", "get-url", "origin"], pasta)[0]:
        _git(["remote", "add", "origin", f"https://github.com/{repo}.git"], pasta)

    # o token vai só por variável de ambiente desta execução (não fica salvo no .git/config)
    cred = _b64.b64encode(f"x-access-token:{vault.get_key('github_token')}".encode()).decode()
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_COUNT": "2",
           "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader", "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {cred}",
           "GIT_CONFIG_KEY_1": "credential.helper", "GIT_CONFIG_VALUE_1": ""}
    _, branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], pasta)
    cod, out = _git(["push", f"https://github.com/{repo}.git", f"HEAD:refs/heads/{branch or 'main'}"], pasta, env)
    if cod:
        dica = DICA_TOKEN if re.search(r"403|denied|Authentication", out) else ""
        return f"{commit}, mas o push falhou: {out[-400:]}\n{dica}"
    return f"{commit} e enviado para https://github.com/{repo} (branch {branch or 'main'})"
