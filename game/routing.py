
from django.urls import path

from . import consumers

websocket_urlpatterns = [
    # ws://.../ws/room/<room_id>/
    path("ws/rooms/<str:room_code>/", consumers.RoomConsumer.as_asgi()),
]
