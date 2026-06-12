"""Rutas de la pantalla Certificados (Forge UI) — cableado en PASO 14.

El name CANÓNICO del listado es ``certificate-list`` (en ``certificates/``),
registrado por ``apps/web/urls.py`` apuntando a ``CertificateListForgeView``.
Aquí ``certificate-list-forge`` (en ``certificados/``) se conserva como alias
histórico de la MISMA vista para los tests aislados
(``apps.web.test_urls_certificados``), sin duplicar el name canónico.
Las acciones (``cert-create``, ``cert-bulk``, ``cert-export``, ``cert-test``)
viven aquí y se incluyen tal cual.
"""
from django.urls import path

from .views_certificates import (
    CertificateBulkView,
    CertificateCreateView,
    CertificateExportView,
    CertificateListForgeView,
    CertificateTestView,
    CertSnoozeView,
    CertToggleActiveView,
)

urlpatterns = [
    path("certificados/", CertificateListForgeView.as_view(), name="certificate-list-forge"),
    path("certificados/nuevo/", CertificateCreateView.as_view(), name="cert-create"),
    path("certificados/bulk/", CertificateBulkView.as_view(), name="cert-bulk"),
    path("certificados/exportar/", CertificateExportView.as_view(), name="cert-export"),
    path("certificados/<int:pk>/probar/", CertificateTestView.as_view(), name="cert-test"),
    path("certificados/<int:pk>/toggle-monitoreo/", CertToggleActiveView.as_view(), name="cert-toggle-active"),
    path("certificados/<int:pk>/silenciar/", CertSnoozeView.as_view(), name="cert-snooze"),
]
