from django.contrib import admin

from .models import ScheduledReport


@admin.register(ScheduledReport)
class ScheduledReportAdmin(admin.ModelAdmin):
    list_display = ("name", "template", "frequency", "output_format", "team", "is_active", "last_run_at")
    list_filter = ("template", "frequency", "is_active")
    search_fields = ("name",)
