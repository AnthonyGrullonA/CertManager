# CertManager — Primera visibilidad en VDI corporativa (sin admin)

Guía para **mostrar el aplicativo** en una VDI/escritorio Windows corporativo
**sin permisos de administrador**. Es para una demo/primer vistazo, no producción.

## Por qué funciona sin admin

`install_windows.bat` / `run_windows.bat` **no necesitan admin**: usan un
**virtualenv por-usuario** (en tu carpeta), **SQLite** (sin BD que provisionar),
un **puerto alto** (8000, no privilegiado) y **no instalan servicios del sistema**
(nada de systemd/nginx/IIS). Todo corre como tu usuario.

## Pasos

### 0. Python (sin admin)
Si `python` no está disponible, instálalo **para tu usuario** (no requiere admin):
- **python.org/downloads** → botón **"Install Now"** (instala per-usuario; deja
  marcado *"Add python.exe to PATH"*), **o**
- **Microsoft Store** → *Python 3.x* (también per-usuario).

### 1. Traer el código (sin admin)
- `git clone https://github.com/AnthonyGrullonA/CertManager.git` (si tienes git), **o**
- Descarga el ZIP del repo desde GitHub (**Code → Download ZIP**) y descomprímelo
  en tu carpeta de usuario.

### 2. Instalar y arrancar
Doble clic a **`install_windows.bat`** (o córrelo en una consola). Hace todo:
venv + dependencias + SQLite + Owner + (si pusiste `cert.txt`) migra el monitoreo,
y arranca el server. Te pedirá la **contraseña del Owner**.

```bat
install_windows.bat
```

### 3. Mostrarlo
- **Tú, en la misma VDI:** `http://127.0.0.1:8000/` → **siempre funciona** (no
  depende de red ni firewall). Para la presentación, **compartir pantalla** desde
  tu VDI es lo más seguro (cero dependencias).
- **Otros, desde sus máquinas:** `http://<TU-IP>:8000/` con la IP que muestra
  `ipconfig` al arrancar. **Funciona solo si la red/firewall corporativos permiten
  el entrante al :8000** — ver el gap abajo.

### 4. Re-arrancar luego
Doble clic a **`run_windows.bat`** (no reinstala; levanta el server otra vez).

Login: el Owner que definiste (por defecto `jairol_grullon@claro.com.do`) + la
contraseña que ingresaste.

## El gap de "sin admin" (qué cubre y qué no)

| Necesidad | ¿Necesita admin? | Cómo se cubre |
|-----------|------------------|----------------|
| Instalar Python | No | per-usuario (python.org "Install Now" / Store) |
| Crear venv + deps | No | en tu carpeta de usuario |
| Base de datos | No | SQLite (archivo local) |
| Correr el server | No | `runserver` en `:8000` (puerto alto) |
| Verlo tú mismo | No | `http://127.0.0.1:8000` |
| **Que otros lo abran por la red** | **Sí (firewall)** | el entrante lo controla la **GPO/Firewall corporativo**; si lo bloquean, pídele al **equipo de Red/Plataforma** que abran el `:8000` en tu VDI — **o presenta compartiendo pantalla** y no necesitas nada de eso |

**Notas de VDI corporativa:**
- La **IP suele ser dinámica** (cambia al reconectar la sesión): usa siempre la que
  muestre `ipconfig`, no una fija.
- Muchas VDI tienen el tráfico **VDI-a-VDI segmentado**: aunque el server escuche
  bien, otra máquina puede no llegar. Por eso, para la demo, **compartir pantalla**
  es lo más confiable.

## Importante
Es el **server de desarrollo de Django** (un solo hilo, sin TLS): perfecto para la
**primera visibilidad**, no para uso real ni muchos usuarios. Para producción va
**Linux / Docker / Kubernetes** con NGINX/TLS (ver `CLARO_NECESIDAD/`).
