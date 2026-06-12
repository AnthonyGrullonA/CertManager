"""URLs de Configuración (PASO 11). Se integran en el PASO 14.

Names expuestos: ``settings``, ``settings-panel`` (por sección),
``settings-test-smtp``, ``settings-test-webhook``, ``settings-test-ldap``.
"""
from django.urls import path

from .views_config import (
    SettingsPanelView,
    SettingsView,
    TestLdapView,
    TestSmsView,
    TestSmtpView,
    TestWebhookView,
)

urlpatterns = [
    path("settings/", SettingsView.as_view(), name="settings"),
    path(
        "settings/panel/<str:section>/",
        SettingsPanelView.as_view(),
        name="settings-panel",
    ),
    path("settings/test-smtp/", TestSmtpView.as_view(), name="settings-test-smtp"),
    path(
        "settings/test-webhook/",
        TestWebhookView.as_view(),
        name="settings-test-webhook",
    ),
    path("settings/test-ldap/", TestLdapView.as_view(), name="settings-test-ldap"),
    path("settings/test-sms/", TestSmsView.as_view(), name="settings-test-sms"),
]
