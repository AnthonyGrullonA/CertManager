"""Validadores de contraseña que respetan la política de la organización."""
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _
from django.utils.translation import ngettext


class OrgMinimumLengthValidator:
    """Longitud mínima según ``OrganizationSettings.password_min_length``
    (Configuración → Seguridad). Fallback a 8 si la BD no está lista.

    Reemplaza al ``MinimumLengthValidator`` estático de Django para que el valor
    del panel controle de verdad la política.
    """

    def _min_length(self) -> int:
        try:
            from apps.core.models import OrganizationSettings

            return OrganizationSettings.load().password_min_length or 8
        except Exception:  # noqa: BLE001 - BD no lista / cualquier error
            return 8

    def validate(self, password, user=None):
        m = self._min_length()
        if len(password) < m:
            raise ValidationError(
                ngettext(
                    "La contraseña debe tener al menos %(min)d carácter.",
                    "La contraseña debe tener al menos %(min)d caracteres.",
                    m,
                ),
                code="password_too_short",
                params={"min": m},
            )

    def get_help_text(self):
        return _("Tu contraseña debe tener al menos %(min)d caracteres.") % {
            "min": self._min_length()
        }
