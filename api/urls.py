"""Router DRF que agrega los endpoints de CertForge bajo /api/."""
from rest_framework.routers import DefaultRouter

from .views import AlertViewSet, CertificateViewSet, TeamViewSet

router = DefaultRouter()
router.register("certificates", CertificateViewSet, basename="certificate")
router.register("teams", TeamViewSet, basename="team")
router.register("alerts", AlertViewSet, basename="alert")

urlpatterns = router.urls
