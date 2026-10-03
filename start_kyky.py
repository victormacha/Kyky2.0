"""Inicia a Kyky: sobe o servidor local e abre a interface numa janela de app (Edge)."""
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

URL = "http://127.0.0.1:8765"
BASE = Path(__file__).parent


def servidor_no_ar():
    try:
        urllib.request.urlopen(URL + "/api/auth/state", timeout=1)
        return True
    except Exception:
        return False


def codigo_mudou():
    """True se algum .py foi editado depois que o servidor atual subiu (ou se não dá para saber qual é ele)."""
    pid = BASE / "data" / "server.pid"
    if not pid.exists():
        return True
    inicio = pid.stat().st_mtime
    return any(p.stat().st_mtime > inicio for p in [*BASE.glob("*.py"), *(BASE / "core").glob("*.py")])


def derrubar_servidor():
    pid = BASE / "data" / "server.pid"
    if pid.exists():
        subprocess.run(["taskkill", "/F", "/PID", pid.read_text().strip()], capture_output=True)
    else:   # servidor de uma versão antiga, sem server.pid: acha quem está na porta
        out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True).stdout
        for linha in out.splitlines():
            if ":8765 " in linha and "LISTEN" in linha.upper():
                subprocess.run(["taskkill", "/F", "/PID", linha.split()[-1]], capture_output=True)
    for _ in range(20):
        if not servidor_no_ar():
            break
        time.sleep(0.25)


def garantir_servidor():
    """Sobe o servidor local se ainda não estiver no ar (fica rodando mesmo sem janela).
    Se o código mudou desde que ele subiu, reinicia para carregar a versão nova."""
    (BASE / "data").mkdir(exist_ok=True)
    if servidor_no_ar():
        if not codigo_mudou():
            return
        derrubar_servidor()
    py = Path(sys.executable).with_name("python.exe")  # servidor precisa de stdout; pythonw não tem
    log = open(BASE / "data" / "server.log", "ab")
    subprocess.Popen([str(py if py.exists() else sys.executable), str(BASE / "server.py")], cwd=BASE,
                     stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    for _ in range(40):
        if servidor_no_ar():
            break
        time.sleep(0.5)


def main():
    garantir_servidor()
    for exe in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Google\Chrome\Application\chrome.exe"):
        if os.path.exists(exe):
            subprocess.Popen([exe, f"--app={URL}/?wake=1" if "--wake" in sys.argv else f"--app={URL}", "--window-size=1400,900"])
            return
    import webbrowser
    webbrowser.open(URL + ("/?wake=1" if "--wake" in sys.argv else ""))


if __name__ == "__main__":
    main()
