
import random

from game.engine.night_registry import register_handler
from game.engine.engine import NightEngine

from models import Role

@register_handler("ravenkeeper")
def handle_librarian(engine : NightEngine, pid, selection):
    """
    Ravenkeeper: learns the role of a specific player when dies at night.
    """
    if not engine.get_state_for_player(pid).get("died_at_night", False):
        return

    targets = selection.get("targets") or []
    if not targets:
        return

    target = targets[0]
    r_asg = engine.get_rasg_by_player_id(target)
    role = None

    if engine.is_affected(pid):
        # If the ravenkeeper is affected, its information is wrong.
        role = random.choice(Role.objects.all())
    else:
        role = r_asg.role

    engine.append_private_info(pid, f"La prueba indica que {r_asg.player.alias} podría ser {role.name}.")
    engine.append_night_event({"type": "ravenkeeper", "actor": pid, "target": targets, "role": role.name, "affected": engine.is_affected(pid)})
