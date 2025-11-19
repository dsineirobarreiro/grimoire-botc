
import json
import asyncio
import logging

from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async

from django.utils import timezone

from .models import Room, Player, RoleAssignment
from .engine.engine import NightEngine, GameEngine  # tu motor nocturno (síncrono o asíncrono)

logger = logging.getLogger(__name__)

def _group_name(room_id: str) -> str:
    return f"room_{room_id}"

class RoomConsumer(AsyncJsonWebsocketConsumer):
    """
    Consumer que gestiona:
     - Lobby (join/leave, set alias, upload photo, ready)
     - Inicio de partida (crear roles, asignar)
     - Noche: recibir selections -> resolver noche -> enviar private/public events
     - Día: nominar, votar (brazo), ejecución
    """

    async def connect(self):
        self.room_id = self.scope["url_route"]["kwargs"]["room_code"]
        self.group_name = _group_name(self.room_id)

        # Autorización básica: asegurarnos de que la sala existe
        room = await database_sync_to_async(self._get_room)(self.room_id)
        if not room:
            await self.close()
            return

        # Aceptar conexión
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        # register socket on a Player instance if the user is logged and has player
        # We'll support anonymous: client should send "join" after connect with alias
        await self.send_json({"type": "connected", "room_id": self.room_id})

    async def disconnect(self, code):
        # Remove from group
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        # Optionally mark player offline in DB if we bound socket to a Player (see "join_room")
        if hasattr(self, "player_id"):
            await database_sync_to_async(self._mark_player_disconnected)(self.player_id)

    # -----------------------
    # Receive from client
    # -----------------------
    async def receive_json(self, content, **kwargs):
        """
        Expected messages:
         - {"type":"join", "alias":"Ana"}
         - {"type":"set_alias","alias":"..."}
         - {"type":"ready","is_ready": true}
         - {"type":"start_game"}  (only host)
         - {"type":"night_action", "selection": {...}}
         - {"type":"nominate","target":"<player_id>"}
         - {"type":"confirm_nomination", "confirm": true}
         - {"type":"vote", "vote": true}
         - {"type":"heartbeat"}
        """
        typ = content.get("type")
        if typ == "join":
            await self.handle_join(content)
        elif typ == "set_alias":
            await self.handle_set_alias(content)
        elif typ == "ready":
            await self.handle_ready(content)
        elif typ == "start_game":
            await self.handle_start_game(content)
        elif typ == "night_action":
            await self.handle_night_action(content)
        elif typ == "nominate":
            await self.handle_nominate(content)
        elif typ == "confirm_nomination":
            await self.handle_confirm_nomination(content)
        elif typ == "vote":
            await self.handle_vote(content)
        elif typ == "heartbeat":
            await self.send_json({"type": "pong"})
        else:
            await self.send_json({"type": "error", "message": "Unknown message type"})

    # -----------------------
    # Handlers
    # -----------------------
    async def handle_join(self, content):
        alias = content.get("alias") or "Anon"
        # create Player (or reuse existing based on session/user)
        player = await database_sync_to_async(self._create_or_get_player)(self.room_id, alias, self.scope.get("user"))
        self.player_id = str(player.id)
        # Optionally store socket id in DB
        await database_sync_to_async(self._bind_socket_to_player)(self.player_id, self.channel_name)

        # broadcast join
        await self.channel_layer.group_send(self.group_name, {
            "type": "player.joined",
            "player": {
                "id": str(player.id),
                "alias": player.alias,
                "photo_url": player.photo_url,
                "is_ready": player.is_ready,
                "is_alive": player.is_alive,
            }
        })

        # send current room state to the player
        room_state = await database_sync_to_async(self._serialize_room)(self.room_id)
        await self.send_json({"type": "room_state", "room": room_state})

    async def handle_set_alias(self, content):
        alias = content.get("alias")
        if not hasattr(self, "player_id"):
            await self.send_json({"type": "error", "message": "Not joined"})
            return
        await database_sync_to_async(self._set_alias)(self.player_id, alias)
        await self.channel_layer.group_send(self.group_name, {
            "type": "player.updated",
            "player": {"id": self.player_id, "alias": alias}
        })

    async def handle_ready(self, content):
        is_ready = bool(content.get("is_ready", True))
        if not hasattr(self, "player_id"):
            await self.send_json({"type": "error", "message": "Not joined"})
            return
        await database_sync_to_async(self._set_ready)(self.player_id, is_ready)

        # broadcast updated players
        players = await database_sync_to_async(self._get_players_for_room)(self.room_id)
        await self.channel_layer.group_send(self.group_name, {
            "type": "lobby.update",
            "players": players
        })

        # If all ready and host triggered auto-start, start game
        all_ready = await database_sync_to_async(self._all_ready)(self.room_id)
        if all_ready:
            # auto-start: run start logic
            await self.handle_start_game({})

    async def handle_start_game(self, content):
        # Only allow host or first player to start - validate
        allowed = await database_sync_to_async(self._is_host_or_room_empty)(self.player_id, self.room_id)
        if not allowed:
            await self.send_json({"type": "error", "message": "Not allowed to start"})
            return

        # Assign roles, build night_queue, etc. Use GameEngine.assign_roles or a service
        await database_sync_to_async(self._setup_game)(self.room_id)

        # Broadcast that game started and send each player their private role via direct message
        room_state = await database_sync_to_async(self._serialize_room)(self.room_id)
        await self.channel_layer.group_send(self.group_name, {
            "type": "game.started",
            "room": room_state
        })

        # Send private roles to each player's channel (requires mapping player->channel_name)
        players = await database_sync_to_async(self._get_players_for_room)(self.room_id)
        for p in players:
            ch_name = await database_sync_to_async(self._get_player_channel)(p["id"])
            if ch_name:
                await self.channel_layer.send(ch_name, {
                    "type": "private.message",
                    "message": {"type": "role", "role": p["role"]}
                })
        # Move to night state
        await database_sync_to_async(self._set_room_state)(self.room_id, "NIGHT")
        await self.channel_layer.group_send(self.group_name, {"type": "phase.change", "phase": "NIGHT"})

    async def handle_night_action(self, content):
        # store the selection for the player, when all selections present resolve night
        selection = content.get("selection", {})
        if not hasattr(self, "player_id"):
            await self.send_json({"type": "error", "message": "Not joined"})
            return
        await database_sync_to_async(self._store_night_action)(self.room_id, self.player_id, selection)

        # check if all players submitted
        all_submitted = await database_sync_to_async(self._all_night_actions_submitted)(self.room_id)
        if all_submitted:
            # get selections and run NightEngine.resolve_night synchronously via DB callable
            selections = await database_sync_to_async(self._gather_night_actions)(self.room_id)
            # run engine (synchronous code) in thread via database_sync_to_async
            results = await database_sync_to_async(self._run_night_engine)(self.room_id, selections)
            # broadcast night results (public)
            await self.channel_layer.group_send(self.group_name, {
                "type": "night.results",
                "results": results["night_events"]
            })
            # send private infos
            for pid, msgs in results["private_info"].items():
                ch_name = await database_sync_to_async(self._get_player_channel)(pid)
                if ch_name:
                    await self.channel_layer.send(ch_name, {
                        "type": "private.message",
                        "message": {"type": "private_info", "messages": msgs}
                    })
            # send deaths summary
            await self.channel_layer.group_send(self.group_name, {
                "type": "night.deaths",
                "deaths": results["deaths"]
            })
            # update DB state etc is already handled by engine
            await database_sync_to_async(self._set_room_state)(self.room_id, "DAY_DISCUSSION")
            await self.channel_layer.group_send(self.group_name, {"type": "phase.change", "phase": "DAY_DISCUSSION"})

    async def handle_nominate(self, content):
        # nominator selects a nominee -> create Nomination in DB with confirmed flags false
        target = content.get("target")
        if not hasattr(self, "player_id"):
            await self.send_json({"type": "error", "message": "Not joined"})
            return
        await database_sync_to_async(self._create_nomination)(self.room_id, self.player_id, target)
        await self.channel_layer.group_send(self.group_name, {
            "type": "nomination.started",
            "nominator": self.player_id,
            "nominee": target
        })

    async def handle_confirm_nomination(self, content):
        confirm = content.get("confirm", True)
        if not hasattr(self, "player_id"):
            return
        await database_sync_to_async(self._confirm_nomination)(self.room_id, self.player_id, confirm)
        # If both confirmed, start voting
        both = await database_sync_to_async(self._nomination_both_confirmed)(self.room_id)
        if both:
            # compute voting order and start the voting loop
            order = await database_sync_to_async(self._compute_voting_order)(self.room_id)
            await self.channel_layer.group_send(self.group_name, {
                "type": "voting.started",
                "order": order
            })
            # run the pointer loop (server-controlled)
            await self._run_voting_loop(order)

    async def handle_vote(self, content):
        # Store current player's vote. Note: the server stores the current "latched" vote state.
        vote = bool(content.get("vote", False))
        if not hasattr(self, "player_id"):
            return
        await database_sync_to_async(self._store_vote)(self.room_id, self.player_id, vote)
        # We do not finish voting here; the pointer loop reads the stored vote when pointer passes

    # -----------------------
    # Server-side events (group_send targets)
    # -----------------------
    async def player_joined(self, event):
        await self.send_json({"type": "player.joined", "player": event["player"]})

    async def player_updated(self, event):
        await self.send_json({"type": "player.updated", "player": event["player"]})

    async def lobby_update(self, event):
        await self.send_json({"type": "lobby.update", "players": event["players"]})

    async def game_started(self, event):
        await self.send_json({"type": "game.started", "room": event["room"]})

    async def private_message(self, event):
        await self.send_json({"type": "private", "message": event["message"]})

    async def phase_change(self, event):
        await self.send_json({"type": "phase.change", "phase": event["phase"]})

    async def night_results(self, event):
        await self.send_json({"type": "night.results", "events": event["results"]})

    async def night_deaths(self, event):
        await self.send_json({"type": "night.deaths", "deaths": event["deaths"]})

    async def nomination_started(self, event):
        await self.send_json({"type": "nomination.started", "nominator": event["nominator"], "nominee": event["nominee"]})

    async def voting_started(self, event):
        await self.send_json({"type": "voting.started", "order": event["order"]})

    # -----------------------
    # Voting pointer loop (server-controlled)
    # -----------------------
    async def _run_voting_loop(self, order):
        """
        Itera por el 'order' (lista de player ids), anunciando pointer,
        y leyendo el stored vote for that pid when pointer passes.
        """
        pointer_delay = 1.0  # segundos por jugador, ajustar a tu UX
        votes_counted = {}
        for pid in order:
            # Announce pointer passing
            await self.channel_layer.group_send(self.group_name, {
                "type": "voting.pointer",
                "player": pid
            })
            # Wait the pointer_delay to allow clients to toggle their vote state
            await asyncio.sleep(pointer_delay)

            # Read current latched vote for this player
            vote = await database_sync_to_async(self._read_vote)(self.room_id, pid)
            votes_counted[pid] = vote

        # finish voting
        yes = sum(1 for v in votes_counted.values() if v)
        threshold = await database_sync_to_async(self._compute_execution_threshold)(self.room_id)
        executed = None
        if yes >= threshold:
            # get nominee
            nominee = await database_sync_to_async(self._get_current_nominee)(self.room_id)
            executed = nominee
            await database_sync_to_async(self._execute_player)(self.room_id, nominee)
            await self.channel_layer.group_send(self.group_name, {"type": "execution.result", "executed": executed})
        else:
            await self.channel_layer.group_send(self.group_name, {"type": "execution.result", "executed": None})

        # after execution, check game end
        game_over = await database_sync_to_async(self._check_game_end)(self.room_id)
        if game_over:
            await self.channel_layer.group_send(self.group_name, {"type": "game.over", "result": game_over})
        else:
            # back to NIGHT
            await database_sync_to_async(self._set_room_state)(self.room_id, "NIGHT")
            await self.channel_layer.group_send(self.group_name, {"type": "phase.change", "phase": "NIGHT"})

    # -----------------------
    # DB helpers (sync) — implementa según tus modelos
    # -----------------------
    def _get_room(self, room_id):
        try:
            return Room.objects.get(id=room_id)
        except Room.DoesNotExist:
            return None

    def _create_or_get_player(self, room_id, alias, user):
        room = Room.objects.get(id=room_id)
        # crea player simple y devuelve instancia
        p = Player.objects.create(room=room, alias=alias)
        return p

    def _bind_socket_to_player(self, player_id, channel_name):
        p = Player.objects.get(id=player_id)
        p.socket_id = channel_name
        p.save()

    def _mark_player_disconnected(self, player_id):
        p = Player.objects.get(id=player_id)
        p.socket_id = ""
        p.save()

    def _serialize_room(self, room_id):
        room = Room.objects.get(id=room_id)
        players = [{
            "id": str(p.id),
            "alias": p.alias,
            "is_ready": p.is_ready,
            "is_alive": p.is_alive,
            "photo": p.photo_url,
            "role": getattr(p.role_assignment.role.name, "role", None) if hasattr(p,"role_assignment") else None
        } for p in room.players.all()]
        return {
            "id": str(room.id),
            "state": room.state,
            "players": players,
            "script": room.script.name,
            "active_night_queue": room.active_night_queue
        }

    def _get_players_for_room(self, room_id):
        room = Room.objects.get(id=room_id)
        return [{
            "id": str(p.id),
            "alias": p.alias,
            "is_ready": p.is_ready,
            "is_alive": p.is_alive,
            "photo": p.photo_url,
            "role": p.role_assignment.role.name if hasattr(p, "role_assignment") else None
        } for p in room.players.all()]

    def _set_alias(self, player_id, alias):
        p = Player.objects.get(id=player_id)
        p.alias = alias
        p.save()

    def _set_ready(self, player_id, is_ready):
        p = Player.objects.get(id=player_id)
        p.is_ready = is_ready
        p.save()

    def _all_ready(self, room_id):
        room = Room.objects.get(id=room_id)
        return all(p.is_ready for p in room.players.all())

    def _is_host_or_room_empty(self, player_id, room_id):
        # Placeholder: check if player is host
        room = Room.objects.get(id=room_id)
        first_player = room.players.first()
        return str(first_player.id) == str(player_id)

    def _setup_game(self, room_id):
        # Initialize GameEngine, assign roles, build active_night_queue, persist as room.active_night_queue
        room = Room.objects.get(id=room_id)
        players = list(room.players.all())
        engine = GameEngine(room)
        engine.assign_roles()  # this should persist RoleAssignment per Player
        # build active_night_queue: first night
        first_queue = engine.get_night_queue(first_night=True)
        room.active_night_queue = first_queue
        room.save()
        return True

    # Night action storage (simple example using a NightAction model or cache)
    def _store_night_action(self, room_id, player_id, selection):
        # Implement: store action in DB table NightAction(room, player, json)
        from .models import NightAction
        NightAction.objects.update_or_create(room_id=room_id, player_id=player_id, defaults={"selection": selection})

    def _all_night_actions_submitted(self, room_id):
        from .models import NightAction
        room = Room.objects.get(id=room_id)
        total_players = room.players.count()
        submitted = NightAction.objects.filter(room_id=room_id).count()
        return submitted >= total_players

    def _gather_night_actions(self, room_id):
        from .models import NightAction
        actions = NightAction.objects.filter(room_id=room_id)
        res = {}
        for a in actions:
            res[str(a.player_id)] = a.selection
        return res

    def _run_night_engine(self, room_id, selections):
        """
        Ejecuta tu NightEngine en síncrono (lo llamamos desde thread pool).
        Debe:
          - cargar room, players, role_assignments
          - ejecutar NightEngine.resolve_night
          - aplicar cambios a DB (muertes, poison flags)
        """
        room = Room.objects.get(id=room_id)
        players = list(room.players.all())
        rasgs = {str(p.id): p.role_assignment for p in players}
        engine = NightEngine(room, players, rasgs)
        result = engine.resolve_night(selections, first_night=(room.current_night == 1))
        return result

    def _get_player_channel(self, player_id):
        try:
            p = Player.objects.get(id=player_id)
            return p.socket_id
        except Player.DoesNotExist:
            return None

    # Voting / nomination helpers (placeholders - implement per models)
    def _create_nomination(self, room_id, nominator_id, nominee_id):
        from .models import Nomination
        room = Room.objects.get(id=room_id)
        Nomination.objects.create(room=room, nominator_id=nominator_id, nominee_id=nominee_id)

    def _confirm_nomination(self, room_id, player_id, confirm):
        from .models import Nomination
        nom = Nomination.objects.filter(room_id=room_id).latest("created_at")
        if str(nom.nominator_id) == str(player_id):
            nom.nominator_confirmed = confirm
        if str(nom.nominee_id) == str(player_id):
            nom.nominee_confirmed = confirm
        nom.save()

    def _nomination_both_confirmed(self, room_id):
        from .models import Nomination
        nom = Nomination.objects.filter(room_id=room_id).latest("created_at")
        return nom.nominator_confirmed and nom.nominee_confirmed

    def _compute_voting_order(self, room_id):
        room = Room.objects.get(id=room_id)
        # Return order as list of player ids (use room.player_order if exists)
        if room.player_order:
            return room.player_order
        return [str(p.id) for p in room.players.all()]

    def _store_vote(self, room_id, player_id, vote):
        # Save current "hand raised" state
        from .models import Vote, Nomination
        nom = Nomination.objects.filter(room_id=room_id).latest("created_at")
        Vote.objects.update_or_create(nomination=nom, player_id=player_id, defaults={"voted": vote})

    def _read_vote(self, room_id, player_id):
        from .models import Vote, Nomination
        nom = Nomination.objects.filter(room_id=room_id).latest("created_at")
        try:
            v = Vote.objects.get(nomination=nom, player_id=player_id)
            return v.voted
        except Vote.DoesNotExist:
            return False

    def _compute_execution_threshold(self, room_id):
        # Usually majority of alive players or specific rule
        room = Room.objects.get(id=room_id)
        alive = room.players.filter(is_alive=True).count()
        return (alive // 2) + 1

    def _get_current_nominee(self, room_id):
        from .models import Nomination
        nom = Nomination.objects.filter(room_id=room_id).latest("created_at")
        return str(nom.nominee_id)

    def _execute_player(self, room_id, player_id):
        p = Player.objects.get(id=player_id)
        p.is_alive = False
        p.save()

    def _check_game_end(self, room_id):
        # Implement según reglas: si demon muerto -> good win; si evil control -> evil win; etc.
        return None

    def _set_room_state(self, room_id, state):
        r = Room.objects.get(id=room_id)
        r.state = state
        r.save()
