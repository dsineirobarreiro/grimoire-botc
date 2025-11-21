from typing import Any
from django.shortcuts import render, redirect
from django.urls import reverse
from django.views.generic import TemplateView, FormView, DetailView
from django.http import HttpRequest, HttpResponse, JsonResponse

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from game.models import Room, Script, Player
from game.forms import CreateRoomForm, JoinRoomForm


class IndexView(TemplateView):
    template_name = "game/index.html"

    def get(self, request):
        return render(request, self.template_name)
    
class CreateRoomView(FormView):
    form_class = CreateRoomForm
    template_name = "game/create_room.html"

    def post(self, request: HttpRequest, *args: str, **kwargs: Any) -> HttpResponse:
        form = self.form_class(request.POST)

        if form.is_valid():
            script = form.cleaned_data['script']
            room = Room.objects.create(script=script)

            alias = form.cleaned_data['alias']
            _ = Player.objects.create(room=room, alias=alias)

            request.session["room_id"] = str(room.id)
            request.session["player_alias"] = alias

            return redirect(reverse(f'game:room'))

class JoinRoomView(FormView):
    form_class = JoinRoomForm
    template_name = "game/join_room.html"

    def post(self, request: HttpRequest, *args: str, **kwargs: Any) -> HttpResponse:
        form = self.form_class(request.POST)

        if form.is_valid():
            room_code = form.cleaned_data['code']
            room = Room.objects.get(code=room_code)

            alias = form.cleaned_data['alias']
            _ = Player.objects.create(room=room, alias=alias)

            request.session["room_id"] = str(room.id)
            request.session["player_alias"] = alias

            return redirect(reverse(f'game:room'))

class RoomView(TemplateView):
    template_name = "game/room.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:

        room_id = self.request.session.get("room_id")
        print(room_id)
        player_alias = self.request.session.get("player_alias")

        context = super().get_context_data(**kwargs)
        context["room"] = Room.objects.get(id=room_id)
        context["player"] = Player.objects.get(room=context["room"], alias=player_alias)
        
        return context
    
    def post(self, request: HttpRequest, *args: str, **kwargs: Any) -> HttpResponse:
        # Manejar la lógica para salir de la sala
        room_id = request.session.get("room_id")
        player_alias = request.session.get("player_alias")

        if room_id and player_alias:
            room = Room.objects.get(id=room_id)
            player = Player.objects.get(room=room, alias=player_alias)
            player.delete()

            del request.session["room_id"]
            del request.session["player_alias"]

            # Notificar al WS
            channel_layer = get_channel_layer()
            room_group = f"room_{room.code}"

            async_to_sync(channel_layer.group_send)(
                room_group,
                {
                    "type": "player_left",
                    "player": {
                        "name": player_alias,
                    },
                }
            )

        return redirect(reverse(f'game:index'))

def create_room(request):
    script = Script.objects.filter(name="Trouble Brewing").first()
    room = Room.objects.create(script=script)
    return JsonResponse({"room_code": room.id})
