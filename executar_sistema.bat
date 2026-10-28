@echo off
chcp 65001 >nul
echo =========================================================
echo   Iniciando Sistema de Estudo de Viabilidade - GeoSampa
echo =========================================================
cd /d "%~dp0"
.venv\Scripts\streamlit.exe run app.py
pause

