"""URLs del Centro de Alertas y del panel de notificaciones.

Estado compartido: ``resolve`` / ``resolve-all`` (Admin/Owner).
Estado personal: ``read`` / ``read-all`` (cualquier usuario con visibilidad).
Detalle en drawer: ``detail``.
"""
from django.urls import path

from .views_alerts import (
    AlertCenterView,
    AlertDetailView,
    AlertPanelView,
    AlertReadAllView,
    AlertReadView,
    AlertResolveAllView,
    AlertResolveView,
)

urlpatterns = [
    path("alerts/", AlertCenterView.as_view(), name="alert-list"),
    path("alerts/panel/", AlertPanelView.as_view(), name="alert-panel"),
    path("alerts/read-all/", AlertReadAllView.as_view(), name="alert-read-all"),
    path("alerts/resolve-all/", AlertResolveAllView.as_view(), name="alert-resolve-all"),
    path("alerts/<int:pk>/detail/", AlertDetailView.as_view(), name="alert-detail"),
    path("alerts/<int:pk>/read/", AlertReadView.as_view(), name="alert-read"),
    path("alerts/<int:pk>/resolve/", AlertResolveView.as_view(), name="alert-resolve"),
]
