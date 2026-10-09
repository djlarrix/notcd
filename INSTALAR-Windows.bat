@echo off
chcp 65001 >nul
rem Ejecuta el instalador de un comando (descarga la ultima version desde GitHub).
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/djlarrix/notcd/main/instalar.ps1 | iex"
echo.
pause
