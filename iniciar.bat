@echo off
REM Sistema de Faturamento CONAP - uso no proprio computador
REM Na primeira vez cria o ambiente Python; a cada abertura confere as dependencias (rapido se ja estao la).
chcp 65001 >nul
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (set PY=py -3) else (set PY=python)

if not exist ".venv\Scripts\python.exe" (
    echo Preparando o ambiente pela primeira vez...
    %PY% -m venv .venv || goto erro
    ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
)
REM Sempre: depois de um "git pull" podem ter entrado dependencias novas.
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt || goto erro
if not exist ".env" copy ".env.exemplo" ".env" >nul

".venv\Scripts\python.exe" servidor.py
goto fim

:erro
echo.
echo Nao foi possivel preparar o ambiente. Verifique se o Python 3.11 ou superior esta instalado
echo (https://www.python.org/downloads/ - marque "Add python.exe to PATH").
pause
:fim
