@echo off
REM ============================================================================
REM run_windows.bat - Arranca CertManager en Windows accesible desde la RED.
REM
REM   Como `python manage.py runserver` pero escuchando en TODAS las interfaces
REM   (0.0.0.0), para que otras maquinas de la red lo abran por la IP del equipo.
REM   Perfil standalone (SQLite). Requiere haber corrido install_windows.bat antes
REM   (venv + BD + Owner). NO instala nada: solo levanta el server.
REM
REM   Puerto: 8000 por defecto, o el que pongas en la variable PORT.
REM   Uso:  doble clic, o:  set PORT=9000 ^&^& run_windows.bat
REM
REM   NOTA: es el server de DESARROLLO de Django (para pruebas internas, pocos
REM   usuarios). Para produccion usa Linux/Docker/K8s (ver CLARO_NECESIDAD).
REM ============================================================================
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
  echo ERROR: no existe el entorno .venv. Corre primero install_windows.bat
  exit /b 1
)
call ".venv\Scripts\activate.bat"

set "DJANGO_SETTINGS_MODULE=config.settings.standalone"
set "CERTFORGE_DATA_DIR=%cd%\data"
set "OBSFORGE_ENABLED=0"
if "%PORT%"=="" set "PORT=8000"

echo ============================================================
echo  CertManager accesible desde la RED (todas las interfaces)
echo  Puerto: %PORT%
echo  Tu(s) IP(s) en la LAN:
ipconfig | findstr /C:"IPv4"
echo  Desde otra maquina:  http://^<TU-IP^>:%PORT%/
echo  (Windows puede pedir permitir Python en el Firewall: pulsa Permitir.)
echo  Si no abre desde otra maquina, crea la regla de Firewall:
echo     netsh advfirewall firewall add rule name="CertManager" dir=in action=allow protocol=TCP localport=%PORT%
echo ============================================================

python manage.py runserver 0.0.0.0:%PORT%
endlocal
