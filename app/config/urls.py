"""Route the demonstration page and question API."""

from django.urls import path

from app.assistant import views

urlpatterns = [
    path("", views.home, name="home"),
    path("ask", views.ask, name="ask"),
]
