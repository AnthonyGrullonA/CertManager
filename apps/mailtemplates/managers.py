from django.db import models


class EmailTemplateQuerySet(models.QuerySet):
    def usable(self, kind=None):
        """Plantillas activas (uso global, sin filtrar por grupo/autoría)."""
        qs = self.filter(is_active=True)
        if kind:
            qs = qs.filter(kind=kind)
        return qs


class EmailTemplateManager(models.Manager.from_queryset(EmailTemplateQuerySet)):
    pass
