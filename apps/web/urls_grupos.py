"""Rutas de la pantalla Grupos (Forge UI)."""
from django.urls import path

from .views_grupos import (
    TeamCreateView,
    TeamDetailView,
    TeamEditView,
    TeamListView,
    TeamMemberAddView,
    TeamMemberRemoveView,
    TeamMemberRoleView,
)

urlpatterns = [
    path("grupos/", TeamListView.as_view(), name="team-list"),
    path("grupos/nuevo/", TeamCreateView.as_view(), name="team-create"),
    path("grupos/<int:pk>/", TeamDetailView.as_view(), name="team-detail"),
    path("grupos/<int:pk>/editar/", TeamEditView.as_view(), name="team-edit"),
    path(
        "grupos/<int:pk>/miembros/agregar/",
        TeamMemberAddView.as_view(),
        name="team-member-add",
    ),
    path(
        "grupos/<int:pk>/miembros/<int:user_id>/rol/",
        TeamMemberRoleView.as_view(),
        name="team-member-role",
    ),
    path(
        "grupos/<int:pk>/miembros/<int:user_id>/quitar/",
        TeamMemberRemoveView.as_view(),
        name="team-member-remove",
    ),
]
