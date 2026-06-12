"""Rutas de gestión de API keys (Owner) y documentación de la API."""
from django.urls import path

from .views_apikeys import (
    ApiDocsView,
    ApiKeyCreateView,
    ApiKeyRevokeView,
    ApiKeysView,
    ApiKeyUsageView,
)

urlpatterns = [
    path("settings/api/", ApiKeysView.as_view(), name="api-keys"),
    path("settings/api/create/", ApiKeyCreateView.as_view(), name="api-key-create"),
    path("settings/api/<int:pk>/revoke/", ApiKeyRevokeView.as_view(), name="api-key-revoke"),
    path("settings/api/<int:pk>/uso/", ApiKeyUsageView.as_view(), name="api-key-usage"),
    path("developers/api/", ApiDocsView.as_view(), name="api-docs"),
]
