@echo off
REM Sistema de Faturamento CONAP - liberado para a rede do escritorio (Fase 3)
REM As colegas acessam pelo navegador em http://IP-DESTE-PC:5000
REM Na primeira vez o Windows pergunta sobre o Firewall: permita em "Redes privadas".
chcp 65001 >nul
cd /d "%~dp0"
set HOST=0.0.0.0
echo.
echo Enderecos deste computador (use o IPv4 da rede do escritorio):
ipconfig | findstr /i "IPv4"
echo As colegas devem abrir: http://SEU-IP:5000
echo.
call iniciar.bat
