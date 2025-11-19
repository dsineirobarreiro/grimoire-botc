
from game.engine.night_registry import register_handler
from game.engine.engine import NightEngine

@register_handler("monk")
def handle_monk(engine : NightEngine, pid, selection):
    """
    Monk: protects a target from demon actions.
    """
    targets = selection.get("targets") or []
    if not targets:
        return

    target = targets[0]
    if target and not engine.is_affected(pid):
        engine.set_state_for_player(target, "protected", True)
    
    engine.append_night_event({"type": "monk", "actor": pid, "target": targets, "affected": engine.is_affected(pid)})