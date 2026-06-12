@echo off
REM ============================================================================
REM install_windows.bat - CertManager para PRUEBAS / MIGRACION local (SQLite).
REM
REM   - Perfil standalone (SQLite automatico, sin MySQL).
REM   - venv + dependencias + migra la BD SQLite.
REM   - Carga Owner + configuracion por defecto Y MIGRA EL MONITOREO desde el
REM     cert.txt si esta en la raiz (data_update_certs_app).
REM   - Arranca el server de desarrollo en http://127.0.0.1:8000/
REM   - NO usar en produccion: es para validar/migrar localmente.
REM
REM Requisitos: Python 3.11+ en el PATH. (Node.js opcional, para el CSS.)
REM Coloca tu cert.txt en la raiz ANTES de correr para migrar todo el monitoreo.
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

REM --- Owner + configuracion (+ migracion del monitoreo desde cert.txt) -------
if "%CF_OWNER_EMAIL%"=="" set "CF_OWNER_EMAIL=jairol_grullon@claro.com.do"
if "%CF_OWNER_PASSWORD%"=="" set /p "CF_OWNER_PASSWORD=Contrasena para el Owner (%CF_OWNER_EMAIL%): "

if exist "cert.txt" (
  echo ^>^> Migrando el monitoreo desde cert.txt ^(Owner + configuracion + certificados^) ...
  python manage.py data_update_certs_app --source cert.txt
) else (
  echo ^>^> No hay cert.txt en la raiz: cargo solo Owner + configuracion.
  echo    Coloca tu cert.txt en la raiz y vuelve a correr para MIGRAR el monitoreo.
  python manage.py data_update_certs_app --skip-certs
)
if errorlevel 1 ( echo ERROR cargando datos. & exit /b 1 )

echo.
echo ^>^> Listo. Entra en http://127.0.0.1:8000/ con el Owner %CF_OWNER_EMAIL%.
echo ^>^> Arrancando ^(Ctrl+C para detener^) ...
python manage.py runserver 127.0.0.1:8000

endlocal
