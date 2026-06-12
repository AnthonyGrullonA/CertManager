@echo off
REM ============================================================================
REM install_windows.bat - CertManager para PRUEBAS en Windows con SQLite.
REM
REM   - Perfil standalone (SQLite automatico, sin MySQL, sin secretos).
REM   - Crea un virtualenv, instala dependencias, migra y arranca el servidor
REM     de desarrollo en http://127.0.0.1:8000/
REM   - NO usar en produccion: es solo para validar el aplicativo localmente.
REM
REM Requisitos: Python 3.11+ en el PATH. (Node.js es opcional, para el CSS.)
REM Uso:  doble clic, o en una consola:  install_windows.bat
REM ============================================================================
setlocal
cd /d "%~dp0"
echo == CertManager - prueba local en Windows (SQLite) ==

where python >nul 2>nul
if errorlevel 1 (
  echo ERROR: Python no esta en el PATH. Instala Python 3.11+ y reintenta.
  exit /b 1
)

if not exist ".venv" (
  echo ^>^> Creando entorno virtual .venv ...
  python -m venv .venv
)
call ".venv\Scripts\activate.bat"

echo ^>^> Instalando dependencias (sin MySQL) ...
python -m pip install --upgrade pip
pip install -r requirements\base.txt
if errorlevel 1 ( echo ERROR instalando dependencias. & exit /b 1 )

REM Configuracion de entorno para SQLite / standalone
set "DJANGO_SETTINGS_MODULE=config.settings.standalone"
set "CERTFORGE_DATA_DIR=%cd%\data"
set "OBSFORGE_ENABLED=0"

REM CSS (Tailwind): se compila si hay npm; si no, la UI puede verse sin estilos.
where npm >nul 2>nul
if not errorlevel 1 (
  if not exist "static\css\forge.css" (
    echo ^>^> Compilando CSS con npm ...
    call npm ci
    call npm run build:css
  )
) else (
  echo (Aviso: no hay npm; si no existe static\css\forge.css la UI se vera sin estilos.)
)

echo ^>^> Aplicando migraciones (crea la BD SQLite) ...
python manage.py migrate --no-input
if errorlevel 1 ( echo ERROR en migrate. & exit /b 1 )

echo ^>^> Recolectando estaticos ...
python manage.py collectstatic --no-input

echo.
echo ^>^> Si es la primera vez, crea un usuario administrador en otra consola:
echo        .venv\Scripts\activate.bat ^&^& python manage.py createsuperuser
echo.
echo ^>^> Arrancando en http://127.0.0.1:8000/  (Ctrl+C para detener)
python manage.py runserver 127.0.0.1:8000

endlocal
