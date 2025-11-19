
import random

from game.engine.night_registry import register_handler
from game.engine.engine import NightEngine

from models import Role

@register_handler("librarian")
def handle_librarian(engine : NightEngine, pid, selection):
    """
    Librarian: learns between two targets if there is a specific outsider.
    """

    outsiders = []
    player = None

    if engine.is_affected(pid):
        # If the librarian is affected, her information is wrong.
        outsiders = Role.objects.filter(alignment='outsider')
        player = engine.get_random_player_excluding([pid])
    else:
        outsiders = engine.get_roles_by_alignment('outsider')
        player = engine.get_player_by_role_name(role.role.name)

    role = random.choice(outsiders)
    not_player = engine.get_random_player_excluding([player.id, pid])

    engine.append_private_info(pid, f"La prueba indica que {player} o {not_player} podría ser {role.name}.")
    engine.append_night_event({"type": "librarian_check", "actor": pid, "target": [player.id, not_player.id], "role": role.name, "affected": engine.is_affected(pid)})
