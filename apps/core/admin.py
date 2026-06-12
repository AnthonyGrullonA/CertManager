from django.contrib import admin

from .models import (
    ApiKey,
    AuditLog,
    LdapConfiguration,
    OrganizationSettings,
    SmsGatewayConfig,
)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Auditoría: solo lectura (append-only). No se crea/edita/borra a mano."""

    list_display = ("created_at", "actor_email", "action", "model", "object_repr", "ip")
    list_filter = ("action", "model", "created_at")
    search_fields = ("actor_email", "object_repr", "object_id", "ip")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LdapConfiguration)
class LdapConfigurationAdmin(admin.ModelAdmin):
    list_display = ("__str__", "server_uri", "enabled", "last_test_ok", "last_test_at")


@admin.register(SmsGatewayConfig)
class SmsGatewayConfigAdmin(admin.ModelAdmin):
    list_display = ("__str__", "ftp_host", "enabled")


@admin.register(OrganizationSettings)
class OrganizationSettingsAdmin(admin.ModelAdmin):
    list_display = ("org_name", "timezone", "check_interval_hours")
    # Los secretos SMTP no se muestran en listados.


@admin.register(ApiKey)
class ApiKeyAdmin(admin.ModelAdmin):
    list_display = ("name", "key_id", "scope", "created_by", "is_active", "last_used_at")
    list_filter = ("scope", "is_active")
    search_fields = ("name", "key_id")
    # El secreto nunca se almacena en claro; solo el hash (no editable).
    readonly_fields = ("prefix", "key_id", "hashed_key", "last_used_at")
