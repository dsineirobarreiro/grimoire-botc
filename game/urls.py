from django.urls import path, register_converter

from . import views

app_name = "game"

urlpatterns = [
    path("", views.IndexView.as_view(), name="index"),
    path("create-room/", views.CreateRoomView.as_view(), name="create_room"),
    path("join-room/", views.JoinRoomView.as_view(), name="join_room"),
    path("room/", views.RoomView.as_view(), name="room"),
    path("api/create-room/", views.create_room),
]