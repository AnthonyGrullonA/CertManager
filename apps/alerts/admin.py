from django.contrib import admin

from .models import Alert, AlertDelivery, AlertUserState, WebhookIntegration


class DeliveryInline(admin.TabularInline):
    model = AlertDelivery
    extra = 0
    readonly_fields = ("channel", "target", "status", "sent_at", "error")


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ("certificate", "severity", "status", "created_at")
    list_filter = ("severity", "status")
    search_fields = ("certificate__domain", "message")
    inlines = [DeliveryInline]


@admin.register(AlertUserState)
class AlertUserStateAdmin(admin.ModelAdmin):
    list_display = ("alert", "user", "read_at", "dismissed_at")
    list_filter = ("read_at", "dismissed_at")
    search_fields = ("alert__certificate__domain", "user__email")


@admin.register(WebhookIntegration)
class WebhookIntegrationAdmin(admin.ModelAdmin):
    list_display = ("name", "webhook_type", "team", "is_active", "rich_format")
    list_filter = ("webhook_type", "is_active", "rich_format")
