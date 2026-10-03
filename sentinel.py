"""Vigia da Kyky: fica ouvindo o microfone e abre o app com 2 palmas, 3 estalos de dedo ou ao dizer "Kyky".
Tudo roda LOCAL: o áudio não é gravado nem enviado para lugar nenhum, só analisado em memória.

Uso:  python sentinel.py                 (fica rodando)
      python sentinel.py --instalar      (inicia junto com o Windows)
      python sentinel.py --desinstalar   (remove da inicialização)
      python sentinel.py --sensibilidade 0.5   (0.1 muito sensível ... 1.0 pouco; padrão 0.5)
Palavra de ativação ("Kyky"): coloque um modelo Vosk em português na pasta models/vosk-pt."""
import json
import os
import socket
import threading
import subprocess
import sys
import time
from pathlib import Path
import numpy as np

BASE = Path(__file__).parent
SR = 16000
FRAME = 160  # 10 ms
STARTUP = Path(os.environ.get("APPDATA", ".")) / "Microsoft/Windows/Start Menu/Programs/Startup" / "KykySentinel.bat"


class Detector:
    """Conta transientes curtos (palma/estalo). 2 ou 3 regulares seguidos de silêncio = ativação."""

    def __init__(self, sens=0.5):
        self.k = 3 + sens * 8          # quantas vezes acima do ruído de fundo
        self.floor = 0.03 + sens * 0.05  # volume mínimo absoluto
        self.bg, self.hits, self.busy_until, self.loud, self.prev, self.sharp = 1e-3, [], 0.0, 0, 1e-3, False

    def feed(self, frame, t):
        rms = float(np.sqrt(np.mean(frame.astype(np.float32) ** 2)))
        loud = rms > max(self.bg * self.k, self.floor)
        if not loud:
            self.bg = 0.995 * self.bg + 0.005 * max(rms, 1e-4)
            if self.loud:                      # terminou um evento: validar duração
                dur = self.loud * 0.01
                if self.sharp and 0.004 < dur <= 0.12:  # início abrupto e curto = palma/estalo; longo = voz, tosse, música
                    self.hits.append(self.t0)
                self.loud = 0
        else:
            if not self.loud:
                if t < self.busy_until:
                    return None
                self.t0 = t
                self.sharp = rms > 6 * self.prev   # palma sobe de uma vez; sílaba de fala sobe devagar
            self.loud += 1
            if self.loud * 0.01 > 0.25:        # barulho longo cancela a sequência
                self.hits.clear()
                self.busy_until = t + 0.4
        self.prev = max(rms, 1e-4)
        # sequência terminada?
        if self.hits and not self.loud and t - self.hits[-1] > 0.55:
            h, self.hits = self.hits, []
            if len(h) in (2, 3):
                gaps = np.diff(h)
                if gaps.min() > 0.12 and gaps.max() < 0.9 and (gaps.max() - gaps.min()) < 0.45:
                    self.busy_until = t + 1.0
                    return "palmas" if len(h) == 2 else "estalos"
        if self.hits and t - self.hits[0] > 3:  # sequência velha demais
            self.hits.clear()
        return None


def e_chamado(txt):
    """O reconhecedor offline entende 'Quiqui' como 'que que'. Só vale uma fala curta que COMEÇA assim
    (evita disparar com frases como 'o que que você quer')."""
    w = txt.split()
    return 0 < len(w) <= 4 and (w[:2] in (["que", "que"], ["qui", "qui"], ["ki", "ki"]) or w[0] in ("kiki", "quiqui", "kyky"))


def acordar(motivo):
    print(time.strftime("%H:%M:%S"), "→ acordando a Kyky:", motivo, flush=True)
    subprocess.Popen([sys.executable, str(BASE / "start_kyky.py"), "--wake"], cwd=BASE,
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def rodar(sens, pausado=None):
    import sounddevice as sd
    det, ultimo = Detector(sens), 0.0
    pausado = pausado or threading.Event()
    rec = None
    modelo = BASE / "models" / "vosk-pt"
    if modelo.exists():
        try:
            from vosk import KaldiRecognizer, Model, SetLogLevel
            SetLogLevel(-1)
            rec = KaldiRecognizer(Model(str(modelo)), SR)
            print("palavra de ativação 'Kyky' ligada")
        except Exception as e:
            print("sem palavra de ativação:", type(e).__name__)
    print("Vigia ligado: 2 palmas, 3 estalos" + (" ou 'Kyky'" if rec else "") + ". Ctrl+C para sair.", flush=True)
    t = 0.0
    with sd.InputStream(samplerate=SR, channels=1, dtype="float32", blocksize=FRAME) as st:
        while True:
            data, _ = st.read(FRAME)
            if pausado.is_set():
                continue
            f = data[:, 0]
            t += FRAME / SR
            ev = det.feed(f, t)
            if rec and rec.AcceptWaveform((f * 32767).astype(np.int16).tobytes()):
                txt = json.loads(rec.Result()).get("text", "")
                ev = ev or ("voz" if e_chamado(txt) else None)
            if ev and time.time() - ultimo > 20:
                ultimo = time.time()
                acordar(ev)


def main():
    a = sys.argv[1:]
    if a[:1] == ["--instalar"]:
        pyw = Path(sys.executable).with_name("pythonw.exe")
        STARTUP.write_text(f'@echo off\r\ncd /d "{BASE}"\r\nstart "" "{pyw}" "{Path(__file__).resolve()}"\r\n', encoding="utf-8")
        print("Instalado na inicialização do Windows:", STARTUP)
    elif a[:1] == ["--desinstalar"]:
        STARTUP.unlink(missing_ok=True)
        print("Removido da inicialização.")
    else:
        sens = float(a[a.index("--sensibilidade") + 1]) if "--sensibilidade" in a else 0.5
        trava = socket.socket()
        try:
            trava.bind(("127.0.0.1", 8766))   # só uma cópia do vigia por vez
        except OSError:
            print("O vigia já está rodando.")
            return
        sys.path.insert(0, str(BASE))
        import start_kyky
        threading.Thread(target=start_kyky.garantir_servidor, daemon=True).start()
        pausado = threading.Event()
        def vigiar():
            while True:                      # se o microfone falhar, tenta de novo em vez de morrer
                try:
                    rodar(sens, pausado)
                except Exception as e:
                    (BASE / "data").mkdir(exist_ok=True)
                    with open(BASE / "data" / "sentinel.log", "a", encoding="utf-8") as f:
                        f.write(f"{time.strftime('%d/%m %H:%M:%S')} {type(e).__name__}: {e}\n")
                    time.sleep(5)
        threading.Thread(target=vigiar, daemon=True).start()
        bandeja(pausado)


def bandeja(pausado):
    """Ícone ao lado do relógio: abrir, pausar a escuta ou sair."""
    try:
        import pystray
        from PIL import Image
    except Exception:
        while True:        # sem bandeja: apenas segue ouvindo
            time.sleep(3600)
    img = Image.open(BASE / "kyky.ico")

    def abrir(icon, item):
        subprocess.Popen([sys.executable, str(BASE / "start_kyky.py")], cwd=BASE,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def alternar(icon, item):
        pausado.clear() if pausado.is_set() else pausado.set()

    def sair(icon, item):
        icon.stop()
        os._exit(0)

    menu = pystray.Menu(
        pystray.MenuItem("Abrir a Kyky", abrir, default=True),
        pystray.MenuItem("Pausar a escuta (palmas, estalos, voz)", alternar, checked=lambda i: pausado.is_set()),
        pystray.MenuItem("Sair", sair))
    pystray.Icon("kyky", img, "Kyky — ouvindo", menu).run()


if __name__ == "__main__":
    main()
