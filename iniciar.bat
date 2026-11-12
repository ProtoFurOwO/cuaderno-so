@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Falta entorno virtual. Sigue README.md o ejecuta instalar.bat.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m streamlit run app.py
pause
