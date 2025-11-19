from django.urls import path
from . import views

app_name = "game"

urlpatterns = [
    path("", views.IndexView.as_view(), name="index"),
    path("api/create-room/", views.create_room),
]