@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY=python"
py -3 -c "import sys" >nul 2>nul && set "PY=py -3"
%PY% configurar.py
pause
