"""Almacenamiento de estáticos tolerante para producción.

``CompressedManifestStaticFilesStorage`` (WhiteNoise) aborta ``collectstatic``
si un asset referencia un archivo ausente — p.ej. ``chart.umd.min.js`` termina en
``//# sourceMappingURL=chart.umd.js.map`` y ese sourcemap no se distribuye.

Esta subclase degrada esa rotura a un warning: si una referencia no se puede
resolver durante el post-procesado, deja la URL original sin hashear en vez de
fallar. Mitiga el riesgo del plan ("Manifest rompe el arranque si falta un
asset") sin tocar los assets de vendor.
"""
from __future__ import annotations

from django.contrib.staticfiles.storage import ManifestStaticFilesStorage
from whitenoise.storage import CompressedManifestStaticFilesStorage


class ForgivingManifestStaticFilesStorage(CompressedManifestStaticFilesStorage):
    # Lookups en runtime de archivos sin entrada en el manifest no lanzan.
    manifest_strict = False

    def hashed_name(self, name, content=None, filename=None):
        try:
            return super().hashed_name(name, content, filename)
        except ValueError:
            # Referencia a un archivo inexistente (p.ej. un sourcemap ausente):
            # se conserva el nombre original en vez de abortar collectstatic.
            return name
