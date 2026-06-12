"""Rutas de la pantalla CertDetalle (Forge UI). Cableado real diferido al PASO 14.

Names expuestos: ``cert-detail``, ``cert-detail-tab``, ``cert-notify``,
``cert-edit``. "Probar ahora" reutiliza ``cert-test`` (PASO 7), no se redefine.
"""
from django.urls import path

from .views_detalle import (
    CertDetailTabView,
    CertDetailView,
    CertEditView,
    CertEmailTestView,
    CertNotifyView,
)

urlpatterns = [
    path("certificates/<int:pk>/", CertDetailView.as_view(), name="cert-detail"),
    path(
        "certificates/<int:pk>/tab/<str:tab>/",
        CertDetailTabView.as_view(),
        name="cert-detail-tab",
    ),
    path("certificates/<int:pk>/notify/", CertNotifyView.as_view(), name="cert-notify"),
    path("certificates/<int:pk>/email-test/", CertEmailTestView.as_view(), name="cert-email-test"),
    path("certificates/<int:pk>/editar/", CertEditView.as_view(), name="cert-edit"),
]
