"""Bootstrap fail-open de obsforge para CertForge."""
from __future__ import annotations

import logging
import os

_BOOTSTRAPPED = False


def configure_obsforge() -> None:
    """Configura obsforge si está instalado.

    La observabilidad no debe impedir el arranque de Django. Si la libreria o su
    configuracion fallan, dejamos el logging estandar vivo.
    """
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED or os.environ.get("OBSFORGE_ENABLED", "1").lower() in {"0", "false", "no"}:
        return

    try:
        import obsforge

        service_name = os.environ.get("OTEL_SERVICE_NAME") or os.environ.get(
            "OBSFORGE_SERVICE_NAME", "certmanager"
        )
        environment = os.environ.get("OBSFORGE_ENVIRONMENT") or os.environ.get(
            "CF_ENV", "local"
        )
        obsforge.bootstrap(
            obsforge.ObsforgeSettings(
                service_name=service_name,
                environment=environment,
                # 'prod' por defecto: serializa/etiqueta el JSON como espera Loki en
                # despliegue. Usa OBSFORGE_LOKI_PRESET=dev solo en local.
                loki={"preset": os.environ.get("OBSFORGE_LOKI_PRESET", "prod")},
            )
        )
        obsforge.install_logging_bridge()
        _BOOTSTRAPPED = True
    except Exception:  # noqa: BLE001
        logging.getLogger(__name__).debug("obsforge bootstrap failed", exc_info=True)
