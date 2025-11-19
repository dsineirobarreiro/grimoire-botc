
import random

from game.engine.night_registry import register_handler
from game.engine.engine import NightEngine

@register_handler("fortune_teller")
def handle_fortune_teller(engine : NightEngine, pid, selection):
    """
    Fortune teller: learns between two targets if there is the demon (there is a townfolk that registers as fake demon).
    """

    targets = selection.get("targets") or []
    if not targets:
        return

    demon = False
    red_herring = False

    if engine.is_affected(pid):
        # demon y red_herring randomly reported
        demon = random.choice([True, False])
        red_herring = random.choice([True, False])
    else:
        r_asg = [engine.get_rasg_by_player_id(t) for t in targets]
        demon = any([True for r in r_asg if r.role.alignment == 'demon'])
        red_herring = any([True for r in r_asg if r.is_red_herring])

    if demon or red_herring:
        engine.append_private_info(pid, f"La prueba indica que el demonio podría estar entre ellos.")
    else:
        engine.append_private_info(pid, f"La prueba indica que el demonio no está entre ellos.")

    engine.append_night_event({"type": "fortune_teller_check", "actor": pid, "target": targets, "demon": demon, "red_herring": red_herring, "affected": engine.is_affected(pid)})
