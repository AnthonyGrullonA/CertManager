from django.contrib import admin

from .models import Membership, Team


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0
    autocomplete_fields = ("user",)


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name", "default_threshold_days", "default_critical_days", "created_by")
    search_fields = ("name", "description")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [MembershipInline]


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "team", "role")
    list_filter = ("role", "team")
    search_fields = ("user__email", "team__name")
    autocomplete_fields = ("user", "team")
