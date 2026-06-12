"""ROOT_URLCONF de prueba: urls globales + las de Certificados (aislado del PASO 14)."""
from config.urls import urlpatterns as _base
from apps.web.urls_certificates import urlpatterns as _mine

urlpatterns = _base + list(_mine)
