from django.shortcuts import render
from django.views.generic import TemplateView
from django.http import JsonResponse

from game.models import Room, Script


class IndexView(TemplateView):
    template_name = "game/lobby.html"

    def get(self, request):
        return render(request, self.template_name)

def create_room(request):
    script = Script.objects.filter(name="Trouble Brewing").first()
    room = Room.objects.create(script=script)
    return JsonResponse({"room_code": room.id})
