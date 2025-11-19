
from game.engine.night_registry import register_handler
from game.engine.engine import NightEngine

@register_handler("imp")
def handle_imp(engine : NightEngine, pid, selection):
    """
    Imp: kills a target at night.
    """

    target = selection.get("target")
    if not target:
        return
    
    kill = True

    # Protections
    if engine.get_state_for_player(target)["protected"]:
        kill = False
    if engine.get_rasg_by_player_id(target).role.name == "soldier":
        kill = engine.is_affected(target)

    # Case demon is poisoned
    kill = kill and not engine.is_affected(pid)

    # TODO: Autokill demon

    if kill:
        engine.mark_death(target, pid, "imp_kill")
