"""Rutas de la pantalla Reportes (PASO 13).

NO se incluyen aquí en las urls globales: el cableado real es el PASO 14. Para
probar, ver ``apps/web/test_urls_reportes.py`` (suma estas rutas a las globales).
"""
from django.urls import path

from . import views_reportes as v

urlpatterns = [
    path("reports/", v.report_list, name="report-list"),
    path("reports/preview/", v.report_preview, name="report-preview"),
    path("reports/export/", v.report_export, name="report-export"),
    path("reports/scheduled/new/", v.report_create, name="report-create"),
    path("reports/scheduled/<int:pk>/edit/", v.report_edit, name="report-edit"),
    path("reports/scheduled/<int:pk>/delete/", v.report_delete, name="report-delete"),
    path("reports/scheduled/<int:pk>/preview/", v.report_preview_scheduled, name="report-preview-scheduled"),
    path("reports/scheduled/<int:pk>/test-send/", v.report_test_send, name="report-test-send"),
]
