"""Gera o relatório diário. Uso:  python run_daily.py
Para rodar todo dia automaticamente (Windows):  python run_daily.py --agendar 08:00
Para remover o agendamento:                     python run_daily.py --desagendar"""
import subprocess
import sys
from pathlib import Path
from core import daily

NOME = "KykyRelatorioDiario"


def main():
    args = sys.argv[1:]
    if args[:1] == ["--agendar"]:
        hora = args[1] if len(args) > 1 else "08:00"
        cmd = f'"{sys.executable}" "{Path(__file__).resolve()}"'
        r = subprocess.run(["schtasks", "/Create", "/F", "/TN", NOME, "/TR", cmd, "/SC", "DAILY", "/ST", hora])
        sys.exit(r.returncode)
    if args[:1] == ["--desagendar"]:
        sys.exit(subprocess.run(["schtasks", "/Delete", "/F", "/TN", NOME]).returncode)
    print("Gerando relatório...")
    print("Salvo em:", daily.run())


if __name__ == "__main__":
    main()
