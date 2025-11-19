
from game.engine.night_registry import register_handler
from game.engine.engine import NightEngine

@register_handler("poisoner")
def handle_poisoner(engine : NightEngine, pid, selection):
    """
    Poisoner: poisons a target at night.
    """
    targets = selection.get("targets") or []
    if not targets:
        return

    target = targets[0]
    if target:
        engine.set_state_for_player(target, "poisoned", True)
    
    engine.append_night_event({"type": "poisoner", "actor": pid, "target": targets, "affected": engine.is_affected(pid)})