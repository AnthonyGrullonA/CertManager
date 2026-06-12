from django.urls import path

from . import views

urlpatterns = [
    path("plantillas/", views.MailTemplateListView.as_view(), name="mailtemplate-list"),
    path("plantillas/nueva/", views.MailTemplateCreateView.as_view(), name="mailtemplate-create"),
    path("plantillas/<int:pk>/editar/", views.MailTemplateEditView.as_view(), name="mailtemplate-edit"),
    path("plantillas/<int:pk>/eliminar/", views.MailTemplateDeleteView.as_view(), name="mailtemplate-delete"),
    path("plantillas/preview/", views.MailTemplatePreviewView.as_view(), name="mailtemplate-preview"),
    path("plantillas/<int:pk>/preview/", views.MailTemplateDetailPreviewView.as_view(), name="mailtemplate-detail-preview"),
]
