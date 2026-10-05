"""Configuração inicial da Kyky num PC novo (o instalar.bat chama este arquivo).
Cria os atalhos, liga o vigia das palmas com o Windows, guarda o token do GitHub no cofre do Windows,
publica a Kyky para o celular pelo Tailscale (se estiver instalado) e abre a Kyky."""
import json
import os
import shutil
import subprocess
import sys
import time
from getpass import getpass
from pathlib import Path

BASE = Path(__file__).parent.resolve()
PYW = Path(sys.executable).with_name("pythonw.exe")
PYW = PYW if PYW.exists() else Path(sys.executable)


def titulo(t):
    print("\n" + "=" * 60 + f"\n  {t}\n" + "=" * 60)


def atalho(destino, alvo, args, icone):
    ps = (f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{destino}');"
          f"$s.TargetPath='{alvo}';$s.Arguments='{args}';$s.WorkingDirectory='{BASE}';"
          f"$s.IconLocation='{icone}';$s.Save()")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True)


def main():
    dono = json.loads((BASE / "dono.json").read_text(encoding="utf-8"))
    nome = dono.get("nome", "você")
    titulo(f"Kyky de {nome}: configuração")

    # 1. GitHub (opcional): o token fica no Gerenciador de Credenciais do Windows, não em arquivo
    if "github" in dono.get("recursos", []):
        from core import vault
        if vault.get_key("github_token"):
            print("GitHub: token já configurado.")
        else:
            print("\nGitHub (opcional, Enter para pular).\n"
                  "Crie em: github.com > Settings > Developer settings > Fine-grained tokens > Generate new token\n"
                  "  Repository access: All repositories\n"
                  "  Permissions: Contents, Pull requests, Actions = Read and write; Administration = Read and write")
            tok = getpass("Cole o token (fica oculto): ").strip()
            if tok:
                vault.set_key("github_token", tok)
                print("  guardado no cofre do Windows.")

    # 2. atalhos na Área de Trabalho e no Menu Iniciar
    icone = BASE / "kyky.ico"
    desktop = Path.home() / "Desktop"
    menu = Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs"
    for pasta in (desktop, menu):
        if pasta.exists():
            atalho(pasta / "Kyky.lnk", PYW, f'"{BASE / "start_kyky.py"}"', icone)
    print("\nAtalhos 'Kyky' criados na Área de Trabalho e no Menu Iniciar.")

    # 3. vigia (palmas/estalos = modo foco) iniciando com o Windows
    subprocess.run([sys.executable, str(BASE / "sentinel.py"), "--instalar"], cwd=BASE)
    subprocess.Popen([str(PYW), str(BASE / "sentinel.py")], cwd=BASE,
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    print("Vigia ligado: 2 palmas ou 3 estalos ligam o modo foco.")

    # 4. celular: Tailscale
    titulo("Celular")
    ts = shutil.which("tailscale") or (r"C:\Program Files\Tailscale\tailscale.exe"
                                       if Path(r"C:\Program Files\Tailscale\tailscale.exe").exists() else None)
    if not ts:
        print("Tailscale não instalado. Para usar a Kyky no celular:\n"
              "  1. instale no PC: https://tailscale.com/download (entre com a sua conta)\n"
              "  2. instale o app Tailscale no celular, com a MESMA conta\n"
              "  3. rode este configurador de novo (configurar.bat)")
    else:
        r = subprocess.run([ts, "serve", "--bg", "--yes", "8765"], capture_output=True, text=True, timeout=60)
        saida = (r.stdout or "") + (r.stderr or "")
        if "login.tailscale.com" in saida:
            print("Falta liberar o HTTPS na sua conta do Tailscale. Abra o link abaixo, clique em Enable e rode o configurador de novo:")
            print("  " + next(l.strip() for l in saida.splitlines() if "login.tailscale.com" in l))
        else:
            url = next((l.strip() for l in saida.splitlines() if l.strip().startswith("https://")), "")
            print(f"No celular (com o Tailscale ligado), abra no Chrome:\n  {url or '(veja: tailscale serve status)'}\n"
                  "e toque em ⋮ > Instalar app.")

    # 5. abre a Kyky (no primeiro acesso ela pede para criar a senha)
    titulo("Pronto!")
    print("Abrindo a Kyky. No primeiro acesso, crie a sua senha.\n"
          "Depois, em Ajustes, cadastre a sua voz e escolha a música do modo foco.")
    subprocess.Popen([str(PYW), str(BASE / "start_kyky.py")], cwd=BASE)
    time.sleep(2)


if __name__ == "__main__":
    main()
