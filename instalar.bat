@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
    echo Instala Python 3.12 desde python.org y vuelve a intentar.
    pause
    exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
    py -3.12 -m venv .venv
    if errorlevel 1 (
        echo No se pudo crear el entorno. Instala Python 3.12.
        pause
        exit /b 1
    )
)
".venv\Scripts\python.exe" -m pip install -r requirements-lock.txt
if errorlevel 1 (
    echo Fallo instalacion. Revisa conexion a Internet y version de Python.
    pause
    exit /b 1
)
echo Dependencias listas. Instala y abre Ollama; descarga ambos modelos segun README.md.
echo Despues ejecuta iniciar.bat y pulsa Preparar documentos.
pause
