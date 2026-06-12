from django.contrib import admin

from .models import Certificate, CertificateCheck, CertificateRecipient


class RecipientInline(admin.TabularInline):
    model = CertificateRecipient
    extra = 0


@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    list_display = ("domain", "port", "team", "status", "days_left", "valid_to", "last_checked_at", "is_active")
    list_filter = ("status", "is_active", "team")
    search_fields = ("domain", "issuer", "subject")
    autocomplete_fields = ("team", "created_by")
    inlines = [RecipientInline]
    readonly_fields = (
        "status", "days_left", "valid_from", "valid_to", "issuer", "subject",
        "last_checked_at", "next_check_at", "last_error", "last_check",
    )


@admin.register(CertificateCheck)
class CertificateCheckAdmin(admin.ModelAdmin):
    list_display = ("certificate", "checked_at", "status", "days_left", "latency_ms")
    list_filter = ("status",)
    search_fields = ("certificate__domain",)
    date_hierarchy = "checked_at"


@admin.register(CertificateRecipient)
class CertificateRecipientAdmin(admin.ModelAdmin):
    list_display = ("email", "certificate", "user")
    search_fields = ("email", "certificate__domain")
