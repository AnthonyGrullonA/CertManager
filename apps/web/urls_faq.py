from django.urls import path

from .views_faq import FaqView

urlpatterns = [
    path("ayuda/", FaqView.as_view(), name="faq"),
]
