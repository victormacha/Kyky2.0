"""Gmail somente leitura, via IMAP com SENHA DE APP (não é a sua senha normal).
Precisa de 'gmail_user' (seu endereço) e 'gmail_app_password' (16 letras) no cofre ou em secrets_local.py.
Como gerar: conta Google > Segurança > Verificação em duas etapas (ligada) > Senhas de app.
A Kyky só LÊ o cabeçalho (remetente, assunto, data). Não marca como lido, não apaga, não responde, não envia."""
import imaplib
from email import message_from_bytes
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
from . import vault


def _conn():
    user, pw = vault.get_key("gmail_user"), vault.get_key("gmail_app_password")
    if not user or not pw:
        raise RuntimeError("email não configurado (gmail_user e gmail_app_password)")
    m = imaplib.IMAP4_SSL("imap.gmail.com", 993, timeout=20)
    m.login(user, pw.replace(" ", ""))
    return m


def _h(v):
    try:
        return str(make_header(decode_header(v or ""))).strip()
    except Exception:
        return str(v or "")


def _config():
    import json
    from pathlib import Path
    f = Path(__file__).parent.parent / "mail_filters.json"
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return {"dias": 14, "prioridade_dominios": [], "ignorar_remetentes": [], "ignorar_dominios": []}


def _ids(m, query):
    import unicodedata
    query = unicodedata.normalize("NFD", query).encode("ascii", "ignore").decode()   # IMAP aceita só ASCII
    typ, data = m.search(None, "X-GM-RAW", '"' + query.replace("\\", "\\\\").replace('"', '\\"') + '"')
    return data[0].split() if typ == "OK" and data and data[0] else []


def _linha(m, i):
    typ, msg = m.fetch(i, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
    h = message_from_bytes(msg[0][1])
    de = _h(h["From"]).split("<")[0].strip().strip('"') or _h(h["From"])
    try:
        quando = parsedate_to_datetime(h["Date"]).astimezone().strftime("%d/%m %H:%M")
    except Exception:
        quando = ""
    return f"{quando} | {de[:40]} | {_h(h['Subject'])[:90]}"


def mail_unread(limit=8):
    """Emails IMPORTANTES não lidos: ignora avisos automáticos (regras em mail_filters.json) e destaca a faculdade."""
    cfg = _config()
    m = _conn()
    try:
        m.select("INBOX", readonly=True)            # readonly: nada é marcado como lido
        dias = f"newer_than:{int(cfg.get('dias', 14))}d"
        ign = list(cfg.get("ignorar_remetentes", [])) + list(cfg.get("ignorar_dominios", []))
        filtro = f"-from:({' OR '.join(ign)})" if ign else ""
        assuntos = cfg.get("ignorar_assuntos", [])
        sem_assunto = ("-subject:(" + " OR ".join('"' + x + '"' for x in assuntos) + ")") if assuntos else ""
        total = len(_ids(m, "is:unread category:primary"))
        prio = []
        if cfg.get("prioridade_dominios"):
            prio = _ids(m, f"is:unread {dias} from:({' OR '.join(cfg['prioridade_dominios'])}) {sem_assunto}")
        outros = [i for i in _ids(m, f"is:unread category:primary {dias} {filtro} {sem_assunto}") if i not in prio]
        n = int(limit)
        saida = [f"{len(prio) + len(outros)} emails importantes não lidos nos últimos {cfg.get('dias', 14)} dias "
                 f"(a caixa principal tem {total} não lidos no total, a maioria avisos automáticos)."]
        if prio:
            saida.append("Da faculdade:\n" + "\n".join(_linha(m, i) for i in prio[-n:][::-1]))
        if outros:
            saida.append("De pessoas e outros:\n" + "\n".join(_linha(m, i) for i in outros[-n:][::-1]))
        return "\n".join(saida)
    finally:
        try:
            m.logout()
        except Exception:
            pass
