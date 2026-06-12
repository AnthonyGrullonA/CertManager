#!/usr/bin/env bash
# =============================================================================
# install_docker.sh — Levanta SOLO el contenedor del aplicativo con Docker.
#
# La base de datos MySQL es EXTERNA (la provee Claro): se configura por
# las vars DB_* en CLARO_NECESIDAD/.env. Este script NO levanta ninguna BD.
#
# Requisitos: Docker + Docker Compose v2. Completar antes CLARO_NECESIDAD/.env.
# El TLS lo termina un NGINX/balanceador delante (el contenedor publica en
# 127.0.0.1:8000).
#
# Uso:   ./install_docker.sh                 # build + up
#        ./install_docker.sh down            # bajar
#        ./install_docker.sh logs            # ver logs
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")"

ENV_FILE="CLARO_NECESIDAD/.env"
COMPOSE="docker compose -f docker-compose.app.yml"

[ -f "$ENV_FILE" ] || { echo "ERROR: falta $ENV_FILE. Copia CLARO_NECESIDAD/.env.example y complétalo." >&2; exit 1; }
command -v docker >/dev/null || { echo "ERROR: Docker no está instalado." >&2; exit 1; }

case "${1:-up}" in
  down)  $COMPOSE down ;;
  logs)  $COMPOSE logs -f --tail=100 ;;
  up|"")
    echo ">> Construyendo y levantando el aplicativo (DB externa vía vars DB_*)…"
    $COMPOSE up -d --build
    echo ""
    echo ">> Estado:"; $COMPOSE ps
    echo ""
    echo ">> El aplicativo escucha en 127.0.0.1:8000 (pon un NGINX/LB con TLS delante)."
    echo ">> Salud:  curl -fsS http://127.0.0.1:8000/health/"
    echo ""
    echo ">> Bootstrap (Owner + configuración + certificados):"
    echo "     coloca cert.txt en la raíz y corre:"
    echo "     docker compose -f docker-compose.app.yml exec web ./data_update_certs_app.sh"
    ;;
  *) echo "Uso: $0 [up|down|logs]" >&2; exit 1 ;;
esac
