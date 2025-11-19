
import random

from game.engine.night_registry import register_handler
from game.engine.engine import NightEngine

from models import Role

@register_handler("washerwoman")
def handle_washerwoman(engine : NightEngine, pid, selection):
    """
    Washerwoman: learns between two targets if there is a specific townfolk.
    """

    townfolks = []
    player = None

    if engine.is_affected(pid):
        # If the washerwoman is affected, her information is wrong.
        townfolks = Role.objects.filter(alignment='townsfolk')
        player = engine.get_random_player_excluding([pid])
    else:
        townfolks = engine.get_roles_by_alignment('townsfolk')
        player = engine.get_player_by_role_name(role.role.name)

    role = random.choice(townfolks)
    not_player = engine.get_random_player_excluding([player.id, pid])

    engine.append_private_info(pid, f"La prueba indica que {player} o {not_player} podría ser {role.name}.")
    engine.append_night_event({"type": "washerwoman_check", "actor": pid, "target": [player.id, not_player.id], "role": role.name, "affected": engine.is_affected(pid)})
