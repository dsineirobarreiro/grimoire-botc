
import random
import math

from game.engine.night_registry import register_handler
from game.engine.engine import NightEngine

@register_handler("chef")
def handle_chef(engine : NightEngine, pid, selection):
    """
    Chef: learns if there is evil seating together.
    """

    pairs = 0
    evil = engine.get_roles_by_alignment('demon') + engine.get_roles_by_alignment('minion')

    if engine.is_affected(pid):
        # If the chef is affected, her information is wrong.
        pairs = random.randint(0, math.ceil(len(evil) / 2))
    else:
        # Count pairs of evil players sitting together
        evil_ids = [player.id for player in evil]

    engine.append_private_info(pid, f"Hay {pairs} pareja/as de malos sentados juntos.")
    engine.append_night_event({"type": "chef_check", "actor": pid, "pairs": pairs, "affected": engine.is_affected(pid)})
