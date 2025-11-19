
from enum import Enum

from engine import NightEngine

class GameState(Enum):
    LOBBY = "lobby"
    NIGHT = "night"
    NIGHT_RESOLUTION = "night_resolution"
    DAY_DISCUSSION = "day_discussion"
    NOMINATION = "nomination"
    VOTING = "voting"
    EXECUTION = "execution"
    CHECK_GAME_END = "check_game_end"


class GameStateMachine:

    def __init__(self, room):
        self.room = room
        self.state = room.state
        self.night_number = room.night
        self.current_nomination = None
        self.votes = {}

    # -------------------------------------------
    #     Transiciones de estado
    # -------------------------------------------

    def all_ready(self):
        if self.state != GameState.LOBBY:
            return
        if all(p.ready for p in self.room.players.all()):
            self.start_night(first=True)

    def start_night(self, first=False):
        self.state = GameState.NIGHT
        self.room.state = GameState.NIGHT.value
        self.room.night += 1
        self.room.save()

        # preparar engine
        self.engine = NightEngine(self.room, ...)
        self.broadcast("night_started", first_night=first)

    def submit_night_action(self, player_id, selection):
        # guardar selección
        self.engine.receive_selection(player_id, selection)

        if self.engine.all_submitted():
            self.resolve_night()

    def resolve_night(self):
        self.state = GameState.NIGHT_RESOLUTION
        results = self.engine.resolve()
        self.broadcast("night_results", results=results)

        self.start_day()

    def start_day(self):
        self.state = GameState.DAY_DISCUSSION
        self.room.state = GameState.DAY_DISCUSSION.value
        self.room.save()

        self.broadcast("day_started", day=self.room.day)

        # arrancar timer asíncrono
        self.start_timer(self.room.day_discussion_seconds)

    def start_nomination(self, nominator_id, nominee_id):
        self.state = GameState.NOMINATION
        self.current_nomination = {
            "nominator": nominator_id,
            "nominee": nominee_id,
            "ok_nominator": False,
            "ok_nominee": False,
        }

        self.broadcast("nomination_started", self.current_nomination)

    def confirm_nomination(self, player_id):
        if player_id == self.current_nomination["nominator"]:
            self.current_nomination["ok_nominator"] = True
        if player_id == self.current_nomination["nominee"]:
            self.current_nomination["ok_nominee"] = True

        if (self.current_nomination["ok_nominator"] and
                self.current_nomination["ok_nominee"]):
            self.start_voting()

    def start_voting(self):
        self.state = GameState.VOTING
        order = self.compute_voting_order()
        self.broadcast("voting_started", order=order)

        # iniciar ciclo de flecha
        self.run_voting(order)

    def run_voting(self, order):
        for pid in order:
            self.broadcast("voting_pointer", player=pid)
            self.collect_vote(pid)
        
        self.finish_voting()

    def collect_vote(self, pid):
        # esperar x segundospción del front
        vote = self.votes.get(pid, False)
        self.votes[pid] = vote

    def finish_voting(self):
        yes_votes = sum(1 for v in self.votes.values() if v)
        threshold = self.compute_execution_threshold()

        self.state = GameState.EXECUTION

        if yes_votes >= threshold:
            target = self.current_nomination["nominee"]
            self.execute_player(target)
            executed = target
        else:
            executed = None

        self.broadcast("execution_resolved", {"executed": executed})

        self.check_game_end()

    def execute_player(self, pid):
        p = self.room.players.get(id=pid)
        p.is_alive = False
        p.save()

    def check_game_end(self):
        if self.good_wins():
            self.broadcast("game_over", winner="good")
            return

        if self.evil_wins():
            self.broadcast("game_over", winner="evil")
            return

        # si nadie gana, vuelve la noche
        self.start_night()
