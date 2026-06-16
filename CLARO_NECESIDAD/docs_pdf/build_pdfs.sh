#!/usr/bin/env bash
# Genera los PDFs de los documentos de CLARO_NECESIDAD con la plantilla de marca.
# Requiere: Node/npm + Google Chrome (no descarga Chromium; usa el Chrome del sistema).
# Uso:  ./build_pdfs.sh
set -euo pipefail
cd "$(dirname "$0")"

CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
[ -x "$CHROME" ] || { echo "ERROR: no encuentro Chrome en '$CHROME' (exporta CHROME=...)" >&2; exit 1; }

echo ">> Instalando dependencias (markdown-it + puppeteer-core + mermaid, sin descargar Chromium)…"
export PUPPETEER_SKIP_DOWNLOAD=1
npm install --silent --no-audit --no-fund markdown-it puppeteer-core mermaid >/dev/null 2>&1

echo ">> markdown -> HTML -> PDF…"
CHROME="$CHROME" DOCDATE="$(date +%Y-%m-%d)" node build.mjs

echo ">> Listo. PDFs en $(pwd)"
