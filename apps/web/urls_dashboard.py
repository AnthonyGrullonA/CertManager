"""Rutas del Dashboard Forge UI (PASO 6, cableado en PASO 14).

Names expuestos:
- ``dashboard-check-all``: acción "Chequear todo" atada al scope (POST, HTMX).
- ``dashboard-forge``: alias histórico de la vista del dashboard. El name
  CANÓNICO es ``dashboard`` (en ``''``), registrado directamente por
  ``apps/web/urls.py``; este alias se conserva para los tests aislados
  (``apps.web.test_urls_dashboard``) sin duplicar el name ``dashboard``.
"""
from django.urls import path

from .views_dashboard import DashboardCheckAllView, DashboardView

urlpatterns = [
    path("forge/dashboard/", DashboardView.as_view(), name="dashboard-forge"),
    path("forge/dashboard/check-all/", DashboardCheckAllView.as_view(), name="dashboard-check-all"),
]
