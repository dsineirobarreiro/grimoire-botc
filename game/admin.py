from django.contrib import admin

from game.models import Room, Script, Role, Player

# Register your models here.
admin.site.register(Room)
admin.site.register(Script)
admin.site.register(Role)
admin.site.register(Player)