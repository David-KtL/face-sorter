@echo off
rem Abre face-sorter. La primera vez prepara el entorno y descarga los modelos.
setlocal
title face-sorter
cd /d "%~dp0"

set "VENV_PY=.venv\Scripts\python.exe"

if exist "%VENV_PY%" goto check_models

echo Primera vez: preparando el entorno. Puede tardar unos minutos...
echo.
set "BASE_PY="
py -3.12 --version >nul 2>nul && set "BASE_PY=py -3.12"
if not defined BASE_PY py -3.11 --version >nul 2>nul && set "BASE_PY=py -3.11"
if not defined BASE_PY python --version >nul 2>nul && set "BASE_PY=python"
if not defined BASE_PY (
    echo No se encontro Python. Instala Python 3.11 o 3.12 desde https://www.python.org
    goto fail
)
%BASE_PY% -m venv .venv
if errorlevel 1 goto fail
"%VENV_PY%" -m pip install --upgrade pip
"%VENV_PY%" -m pip install -r requirements.txt
if errorlevel 1 goto fail
"%VENV_PY%" -m pip install -e .
if errorlevel 1 goto fail

:check_models
if not exist "models\face_detection_yunet_2023mar.onnx" goto download_models
if not exist "models\face_recognition_sface_2021dec.onnx" goto download_models
goto launch

:download_models
echo Descargando los modelos de reconocimiento facial (necesita internet, solo esta vez)...
"%VENV_PY%" scripts\download_models.py
if errorlevel 1 goto fail

:launch
rem pythonw abre la ventana sin dejar una consola abierta detras.
start "" ".venv\Scripts\pythonw.exe" -m face_sorter gui
exit /b 0

:fail
echo.
echo No se pudo iniciar face-sorter. Revisa los mensajes de arriba.
pause
exit /b 1
