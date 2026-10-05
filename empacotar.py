"""Gera o .zip da Kyky para outra pessoa (ex: o sócio), SEM nenhum dado seu.

Uso:  python empacotar.py --nome Samuel --sobre "Sócio do Victor." --recursos github,leads,vagas

Entra no zip: o código (o mesmo do GitHub), um dono.json com o nome da pessoa, o instalador e
SÓ as chaves de IA/busca. Nunca entram: data/ (senha, voz, sessões), workspace, memória, perfil,
tokens do GitHub/Canvas e dados do Gmail."""
import argparse
import io
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

BASE = Path(__file__).parent.resolve()
CHAVES_COMPARTILHADAS = ("google", "groq", "openrouter", "mistral", "tavily", "tomtom", "pexels")
NUNCA = re.compile(r"(^|/)(data|workspace|models|reports|dist|__pycache__)/|(^|/)(secrets_local\.py|keys\.txt|dono\.json|profile\.md|"
                   r"candidate\.md|mail_filters\.json|browser_login\.py|.*\.db|models_cache\.json|web/face\.jpg)$", re.I)   # face.jpg = foto do Victor
SEGREDOS_PESSOAIS = ("github_token", "canvas_token", "canvas_url", "gmail_user", "gmail_app_password")


def arquivos_do_codigo():
    """Os mesmos arquivos que vão para o GitHub (respeita o .gitignore), menos os pessoais."""
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=BASE,
                         capture_output=True, text=True, check=True).stdout.splitlines()
    return sorted(f for f in out if (BASE / f).is_file() and not NUNCA.search(f) and f != "empacotar.py")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nome", required=True)
    ap.add_argument("--sobre", default="")
    ap.add_argument("--recursos", default="github,leads,vagas")
    ap.add_argument("--repo", default="")
    ap.add_argument("--cidade", default="sua cidade")
    a = ap.parse_args()

    sys.path.insert(0, str(BASE))
    from core import vault
    chaves = {k: vault.get_key(k) for k in CHAVES_COMPARTILHADAS}
    chaves = {k: v for k, v in chaves.items() if v}
    meus = [vault.get_key(k) for k in SEGREDOS_PESSOAIS]
    meus = [v for v in meus if v and len(v) > 6]

    dono = {"nome": a.nome, "sobre": a.sobre, "repo_proprio": a.repo, "cidade_exemplo": a.cidade,
            "recursos": [r.strip() for r in a.recursos.split(",") if r.strip()]}
    secrets = ('"""Chaves de IA e busca compartilhadas. NÃO suba este arquivo para o git."""\nKEYS = '
               + json.dumps(chaves, indent=4, ensure_ascii=False) + "\n")
    perfil = (f"O nome dele é {a.nome}. {a.sobre}\n\nCOMO CONVERSAR\n- Português do Brasil, direto e natural.\n"
              "- Quando não souber, diga. Quando a tarefa for grande, quebre em passos.\n")
    leia = (f"KYKY DE {a.nome.upper()}\n\n1. Extraia esta pasta para um lugar fixo (ex: Documentos\\Kyky). Não rode de dentro do zip.\n"
            "2. Dê dois cliques em instalar.bat.\n3. Siga as instruções. No primeiro acesso, crie a sua senha.\n\n"
            "Celular: instale o Tailscale (tailscale.com/download) no PC e no celular, com a mesma conta,\n"
            "e rode configurar.bat de novo. Ele mostra o endereço para abrir no celular.\n")

    pasta = f"Kyky-{a.nome}"
    destino = BASE / "dist" / f"{pasta}.zip"
    destino.parent.mkdir(exist_ok=True)
    arqs = arquivos_do_codigo()
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        for f in arqs:
            z.write(BASE / f, f"{pasta}/{f}")
        z.writestr(f"{pasta}/core/secrets_local.py", secrets)
        z.writestr(f"{pasta}/dono.json", json.dumps(dono, indent=2, ensure_ascii=False))
        z.writestr(f"{pasta}/profile.md", perfil)
        z.writestr(f"{pasta}/LEIA-ME.txt", leia.replace("\n", "\r\n"))

    # conferência final: nenhum segredo pessoal pode estar no zip
    with zipfile.ZipFile(destino) as z:
        nomes = z.namelist()
        vazou = [n for n in nomes for s in meus if s in z.read(n).decode("utf-8", "replace")]
        ruins = [n for n in nomes if NUNCA.search(n.split("/", 1)[1]) and not n.endswith(("core/secrets_local.py", "dono.json", "profile.md"))]
    if vazou or ruins:
        destino.unlink()
        sys.exit(f"CANCELADO, o zip teria dados pessoais: {vazou + ruins}")
    print(f"ok: {destino} ({destino.stat().st_size // 1024} KB, {len(nomes)} arquivos)")
    print(f"chaves incluídas: {', '.join(chaves)}")
    print(f"recursos ligados: {', '.join(dono['recursos'])}")


if __name__ == "__main__":
    main()
