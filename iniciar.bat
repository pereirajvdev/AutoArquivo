@echo off
setlocal
title AutoArquivo
cd /d "%~dp0"

if exist ".venv\Scripts\activate.bat" goto :activate

echo [AutoArquivo] Ambiente virtual .venv nao encontrado. Criando...
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 -m venv .venv
) else (
    python -m venv .venv
)
if not exist ".venv\Scripts\activate.bat" (
    echo [ERRO] Nao foi possivel criar o ambiente virtual. Verifique se o Python 3 esta instalado.
    pause
    exit /b 1
)
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERRO] Falha ao instalar as dependencias.
    pause
    exit /b 1
)
goto :run

:activate
call ".venv\Scripts\activate.bat"

:run
python "src\main.py"
if errorlevel 1 (
    echo.
    echo [AutoArquivo] A aplicacao foi encerrada com erro. Veja as mensagens acima.
    pause
)
endlocal
