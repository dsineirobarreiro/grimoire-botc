
from django.urls import re_path

import consumers

websocket_urlpatterns = [
    # ws://.../ws/room/<room_id>/
    re_path(r"ws/room/(?P<room_id>[0-9a-f-]+)/$", consumers.RoomConsumer.as_asgi()),
]
