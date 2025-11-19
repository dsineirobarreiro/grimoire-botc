
import random

from game.engine.night_registry import register_handler
from game.engine.engine import NightEngine

@register_handler("empath")
def handle_empath(engine : NightEngine, pid, selection):
        """
        Empath: learns how many evil players adjacent to them (left/right neighbors).
        """

        cnt = 0

        if engine.is_affected(pid):
            # affected: random number between 0 and 2
            cnt = random.randint(0,2)
        else:
            order = engine.room.player_order or []
            idx = order.index(pid)
            left = order[(idx - 1) % len(order)]
            right = order[(idx + 1) % len(order)]
            for neighbor in (left, right):
                rasg = engine.get_rasg_by_player_id(neighbor)
                if rasg and rasg.role.alignment in ("minion", "demon"):
                    cnt += 1

        engine.append_private_info(pid, f"Has detectado a {cnt} jugador/es malvado/s entre tus vecinos.")