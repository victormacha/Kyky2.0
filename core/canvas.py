"""Canvas (faculdade): leitura de cursos, tarefas e prazos pela API oficial.
Só leitura: a Kyky não entrega nem altera nada. Precisa de 'canvas_url' (ex: https://suafaculdade.instructure.com)
e 'canvas_token' (Canvas > Conta > Configurações > Novo token de acesso) no cofre ou em secrets_local.py."""
from datetime import datetime, timezone
import requests
from . import vault


def _cfg():
    url, tok = vault.get_key("canvas_url"), vault.get_key("canvas_token")
    if not url or not tok:
        raise RuntimeError("configure 'canvas_url' e 'canvas_token' (veja core/canvas.py)")
    return url.rstrip("/"), {"Authorization": f"Bearer {tok}"}


def _get(path, **params):
    url, h = _cfg()
    out, next_url = [], f"{url}/api/v1/{path}"
    params.setdefault("per_page", 50)
    while next_url and len(out) < 300:
        r = requests.get(next_url, headers=h, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        out += data if isinstance(data, list) else [data]
        next_url, params = r.links.get("next", {}).get("url"), None
    return out


def _data(iso):
    if not iso:
        return "sem prazo"
    d = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone()
    return d.strftime("%d/%m %H:%M")


def canvas_courses():
    cs = _get("courses", enrollment_state="active")
    return "\n".join(f"#{c['id']} {c.get('name')}" for c in cs if c.get("name")) or "(nenhum curso ativo)"


def canvas_upcoming(days=14):
    """Tarefas com prazo nos próximos dias e ainda não entregues, em todos os cursos."""
    from concurrent.futures import ThreadPoolExecutor
    agora = datetime.now(timezone.utc)
    cursos = [c for c in _get("courses", enrollment_state="active") if c.get("name")]

    def do_curso(c):
        try:
            return c, _get(f"courses/{c['id']}/assignments", bucket="upcoming", include="submission", order_by="due_at")
        except Exception:
            return c, []

    linhas = []
    with ThreadPoolExecutor(8) as ex:                      # cursos em paralelo
        for c, tarefas in ex.map(do_curso, cursos):
            for a in tarefas:
                due = a.get("due_at")
                if not due:
                    continue
                dt = datetime.fromisoformat(due.replace("Z", "+00:00"))
                if (dt - agora).days > int(days) or (a.get("submission") or {}).get("workflow_state") in ("submitted", "graded"):
                    continue
                linhas.append((dt, f"{_data(due)} | {c['name']} | {a['name']} | {a.get('html_url', '')}"))
    return "\n".join(t for _, t in sorted(linhas)) or "(nada pendente no período)"
