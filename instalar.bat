@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Instalando a Kyky

echo ============================================================
echo   Instalando a Kyky
echo ============================================================
echo.

rem --- 1. Python (precisa ser o de verdade, nao o atalho da Microsoft Store)
set "PY="
py -3 -c "import sys" >nul 2>nul && set "PY=py -3"
if not defined PY python -c "import sys" >nul 2>nul && set "PY=python"
if not defined PY goto sem_python

%PY% -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)" || (
  echo Seu Python e antigo demais. Instale o Python 3.12 ou mais novo.
  goto sem_python
)
echo [1/3] Python encontrado.

rem --- 2. bibliotecas
echo [2/3] Instalando as bibliotecas (pode levar alguns minutos)...
%PY% -m pip install --upgrade pip --quiet --disable-pip-version-check
%PY% -m pip install --quiet --disable-pip-version-check openai keyring ddgs requests fastapi "uvicorn[standard]" websockets edge-tts numpy sounddevice pystray pillow
if errorlevel 1 (
  echo.
  echo Falha ao instalar as bibliotecas. Confira a internet e rode o instalar.bat de novo.
  pause
  exit /b 1
)

rem --- 3. configuracao (atalhos, vigia das palmas, celular)
echo [3/3] Configurando...
%PY% configurar.py
echo.
pause
exit /b 0

:sem_python
echo.
echo O Python nao esta instalado.
choice /c SN /m "Quer que eu instale o Python 3.12 agora (pelo winget da Microsoft)"
if errorlevel 2 (
  echo Instale em https://www.python.org/downloads/ marcando "Add python.exe to PATH" e rode o instalar.bat de novo.
  pause
  exit /b 1
)
winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
echo.
echo Python instalado. FECHE esta janela e abra o instalar.bat de novo.
pause
exit /b 0
