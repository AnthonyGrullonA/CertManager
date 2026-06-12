# =============================================================================
# CertManager — imagen para el stack de observabilidad (demo runnable).
# Multi-stage: 1) compila el CSS (Tailwind/Forge UI) con Node; 2) runtime Python.
# Perfil: config.settings.standalone (SQLite por defecto o DATABASE_URL).
# obsforge es OPCIONAL: pasá --build-arg PIP_EXTRA_INDEX_URL=<índice-privado>
# para incluirlo; sin él, la app emite JSON plano a stdout (igual va a Loki).
# =============================================================================

# --- Stage 1: compilar el CSS -------------------------------------------------
FROM node:20-alpine AS frontend
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
COPY tailwind.config.js postcss.config.js ./
COPY static/ ./static/
COPY templates/ ./templates/
RUN npm run build:css

# --- Stage 2: runtime Python --------------------------------------------------
FROM python:3.13-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=config.settings.standalone \
    CERTFORGE_DATA_DIR=/data \
    LOG_DIR=/var/log/certmanager
WORKDIR /app

# curl para el healthcheck; libmariadb3 es la lib runtime del driver MySQL
# (mysqlclient). Se queda en la imagen; las deps de compilación se quitan abajo.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl libmariadb3 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/ requirements/
ARG PIP_EXTRA_INDEX_URL=""
# Build-deps de mysqlclient (compilador + headers), se instalan, compila pip y se
# purgan en la misma capa para no dejar ~200 MB de toolchain en la imagen final.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential default-libmysqlclient-dev pkg-config \
    && pip install --no-cache-dir -r requirements/docker.txt \
       ${PIP_EXTRA_INDEX_URL:+--extra-index-url "$PIP_EXTRA_INDEX_URL"} \
    && apt-get purge -y --auto-remove build-essential default-libmysqlclient-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Código + CSS compilado del stage frontend.
COPY . .
COPY --from=frontend /app/static/css/forge.css static/css/forge.css

# Usuario no-root + directorios persistentes/escribibles.
RUN useradd -m -u 10001 app \
    && mkdir -p /data /var/log/certmanager \
    && chown -R app:app /app /data /var/log/certmanager
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://localhost:8000/health/ || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", \
     "--workers", "3", "--access-logfile", "-", "--error-logfile", "-"]
