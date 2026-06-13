# Auditoría de refresco HTMX al agregar elementos — 2026-06-12

## Problema

"A veces cuando agrego cosas la pantalla se queda igual y debo recargar."

## Auditoría (todas las acciones de alta/edición vía HTMX)

Mecanismos válidos encontrados y verificados:
- Fila/tbody OOB (`hx-swap-oob`) + reconstrucción de `forge-table.js` en
  `htmx:oobAfterSwap` (certificados, grupos, usuarios).
- `HX-Trigger` con listener real en la página (`cf:certs-changed`,
  `cf:cert-updated`, `cf:team-updated`, `cf:user-updated`,
  `cf:alerts-changed`, `cf:check-all-started`).
- Target directo de la región (miembros de grupo, reportes programados,
  paneles de config, secciones de perfil).
- Estado vacío de Grupos: CSS `:has(#team-rows:empty)` revela la tabla al
  insertar la primera fila (sin JS).

**Único flujo roto: API keys (crear clave).** `ApiKeyCreateView` responde solo
el panel del secreto (`#api-key-result`); la tabla "Claves existentes" no
recibe OOB ni trigger y su `<tbody>` no tiene id. La clave nueva no aparece
hasta recargar.

## Fix

1. `templates/apikeys/list.html`: `<tbody id="key-rows">`; la fila de estado
   vacío recibe `id="keys-empty"`.
2. `templates/apikeys/_created.html`: además del panel del secreto, inserta la
   fila nueva fuera de banda (`<tbody id="key-rows" hx-swap-oob="afterbegin">`
   con `apikeys/_row.html`) y elimina `#keys-empty` (`hx-swap-oob="delete"`).
   `forge-table.js` se reconstruye solo (evento `htmx:oobAfterSwap`).

## Tests

- El POST de crear clave devuelve el secreto Y la fila OOB hacia `key-rows`.
- La lista renderiza `id="key-rows"` y `id="keys-empty"` cuando está vacía.
