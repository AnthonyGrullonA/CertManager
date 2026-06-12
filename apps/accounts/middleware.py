"""Aplica el idioma preferido del usuario (UserPreferences.language).

Hace que el selector de idioma del Perfil sea funcional: activa la traducción de
Django para el usuario autenticado según su preferencia guardada. Las cadenas que
estén traducidas (i18n) se muestran en ese idioma; el español es el idioma base.
"""
from django.utils import translation


class UserLocaleMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        lang = None
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            prefs = getattr(user, "preferences", None)
            lang = getattr(prefs, "language", None)
        if lang:
            translation.activate(lang)
            request.LANGUAGE_CODE = translation.get_language()
        response = self.get_response(request)
        translation.deactivate()
        return response
