from django.urls import path

from app.assistant import views

urlpatterns = [
    path("ask", views.ask, name="ask"),
]
