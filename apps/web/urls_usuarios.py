"""URLs de la pantalla Usuarios (PASO 10, solo Owner).

Names expuestos: ``user-list``, ``user-invite``. La acción de fila
``user-toggle-active`` se anota como follow-up para el paso 14 (no está en el
contrato de names obligatorios, pero la fila la necesita).
"""
from django.urls import path

from .views_usuarios import (
    UserDetailView,
    UserEditView,
    UserInviteView,
    UserListView,
    UserToggleActiveView,
)

urlpatterns = [
    path("users/", UserListView.as_view(), name="user-list"),
    path("users/invite/", UserInviteView.as_view(), name="user-invite"),
    path("users/<int:pk>/", UserDetailView.as_view(), name="user-detail"),
    path("users/<int:pk>/editar/", UserEditView.as_view(), name="user-edit"),
    path(
        "users/<int:pk>/toggle-active/",
        UserToggleActiveView.as_view(),
        name="user-toggle-active",
    ),
]
