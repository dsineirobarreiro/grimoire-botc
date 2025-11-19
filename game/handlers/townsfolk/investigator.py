
import random

from game.engine.night_registry import register_handler
from game.engine.engine import NightEngine

from models import Role

@register_handler("investigator")
def handle_investigator(engine : NightEngine, pid, selection):
    """
    Investigator: learns between two targets if there is a specific minion.
    """

    minions = []
    player = None

    if engine.is_affected(pid):
        # If the investigator is affected, her information is wrong.
        minions = Role.objects.filter(alignment='minion')
        player = engine.get_random_player_excluding([pid])
    else:
        minions = engine.get_roles_by_alignment('minion')
        player = engine.get_player_by_role_name(role.role.name)

    role = random.choice(minions)
    not_player = engine.get_random_player_excluding([player.id, pid])

    engine.append_private_info(pid, f"La prueba indica que {player} o {not_player} podría ser {role.name}.")
    engine.append_night_event({"type": "investigator_check", "actor": pid, "target": [player.id, not_player.id], "role": role.name, "affected": engine.is_affected(pid)})
