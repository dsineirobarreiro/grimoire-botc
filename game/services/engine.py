import random
import logging
from typing import Dict, List

from django.db import transaction

from ..models import Role, Player, Room, RoleAssignment

logger = logging.getLogger(__name__)

class GameEngine:

    def __init__(self, room: Room):
        self.room = room
        self.script = room.script
        self.players = list(room.player_order.all())
        self.roles = list(self.script.roles.all())

    # ---------------------------------------------------------
    # 1. ASIGNACIÓN DE ROLES
    # ---------------------------------------------------------
    def assign_roles(self):
        """
        Asigna a cada jugador un rol válido para Trouble Brewing,
        manejando Outsiders, Baron y Drunk.
        """

        num_players = len(self.players)

        # 1) Distribución estándar BOTC (Trouble Brewing)
        # Fuente oficial: Handbook BOTC
        setup_chart = {
            5:  (3, 0, 1, 1),
            6:  (3, 1, 1, 1),
            7:  (5, 0, 1, 1),
            8:  (5, 1, 1, 1),
            9:  (5, 2, 1, 1),
            10: (7, 0, 2, 1),
            11: (7, 1, 2, 1),
            12: (7, 2, 2, 1),
            13: (9, 0, 3, 1),
            14: (9, 1, 3, 1),
            15: (9, 2, 3, 1)
        }

        if num_players not in setup_chart:
            raise ValueError("Número de jugadores no soportado por Trouble Brewing.")

        num_town, num_outsiders, num_minions, num_demons = setup_chart[num_players]

        # -----------------------------------------------------
        # 2. Filtrar roles según categorías
        # -----------------------------------------------------
        townsfolk_roles = [r for r in self.roles if r.alignment == "townsfolk"]
        outsider_roles = [r for r in self.roles if r.alignment == "outsider"]
        minion_roles = [r for r in self.roles if r.alignment == "minion"]
        demon_roles = [r for r in self.roles if r.alignment == "demon"]

        # -----------------------------------------------------
        # 3. Seleccionar roles aleatoriamente
        # -----------------------------------------------------
        selected_townsfolk = random.sample(townsfolk_roles, num_town)
        selected_outsiders = random.sample(outsider_roles, num_outsiders)
        selected_minions = random.sample(minion_roles, num_minions)
        selected_demons = random.sample(demon_roles, num_demons)

        final_roles = (
            selected_townsfolk
            + selected_outsiders
            + selected_minions
            + selected_demons
        )

        # -----------------------------------------------------
        # 4. Aplicar BARON (añade +2 outsiders, -2 townsfolk)
        # -----------------------------------------------------
        has_baron = any(r.name == "Baron" for r in self.roles)

        if has_baron:
            # elegir un Townsfolk para reemplazarlo
            towns_removed = random.sample(selected_townsfolk, 2)
            final_roles.remove(towns_removed)

            outsider_reminder = [r for r in outsider_roles if r not in selected_outsiders]
            final_roles.append(random.sample(outsider_reminder, 2))

        # -----------------------------------------------------
        # 5. Asignar roles a los jugadores en DB
        # -----------------------------------------------------
        random.shuffle(final_roles)

        with transaction.atomic():
            for player, role in zip(self.players, final_roles):
                player.is_alive = True
                player.save()

                # Crear RoleAssignment
                role_assignment, _ = RoleAssignment.objects.update_or_create(
                    player=player,
                    role=role
                )

                if role.name == "Drunk":
                    # El jugador "Drunk" recibe un rol falso
                    townsfolk_reminder = [r for r in townsfolk_roles if r not in selected_townsfolk]
                    new_townsfolk = random.choice(townsfolk_reminder)
                    role_assignment.drunk_real_role = new_townsfolk
                    role_assignment.save()


    # ---------------------------------------------------------
    # 2. NIGHT ORDER
    # ---------------------------------------------------------
    def get_night_queue(self, first_night=True):
        """
        Devuelve la cola de noche filtrada:
        - Solo roles presentes en la partida
        - Orden oficial del Script
        """
        night_order_raw = (
            self.script.night_order["first_night"]
            if first_night
            else self.script.night_order["other_nights"]
        )

        # roles reales en partida
        alive_roles = {p.role.name for p in self.players}

        filtered = [
            role_name
            for role_name in night_order_raw
            if role_name in alive_roles
        ]

        return filtered

class NightResolutionError(Exception):
    pass


class NightEngine:
    """
    Motor para resolver una noche: recorre el room.active_night_queue (lista de nombres de rol)
    y aplica las acciones en orden usando las selecciones provistas por el frontend.
    """

    def __init__(self, room, players, role_assignments):
        """
        :param room: instancia Room
        :param players: list de Player (instancias) pertenecientes a la sala
        :param role_assignments: dict player_id -> RoleAssignment
        """
        self.room = room
        self.players = {str(p.id): p for p in players}
        self.r_asgs = role_assignments  # dict player_id -> RoleAssignment
        self.state = {pid: {
            "poisoned": False,
            "protected": False,
            "will_die": False,
            "killed_by": None,
            "info": []
        } for pid in self.players.keys()}

        # eventos públicos
        self.night_events = []
        # mensajes privados por jugador
        self.private_info = {pid: [] for pid in self.players.keys()}

    # ---------------------------
    # Helpers
    # ---------------------------
    def get_player_by_role_name(self, role_name: str) -> List[Player]:
        """Devuelve lista de jugadores que actualmente tienen un Role con name == role_name y están vivos."""
        result = []
        for pid, rasg in self.r_asgs.items():
            role = rasg.role
            if role.name == role_name and self.players[pid].is_alive:
                result.append(self.players[pid])
        return result

    def is_poisoned(self, player_id: str) -> bool:
        """Comprueba flag persistente (RoleAssignment.is_poisoned) o estado temporal actual."""
        ra = self.r_asgs.get(player_id)
        if ra and getattr(ra, "is_poisoned", False):
            return True
        return self.state[player_id]["poisoned"]

    def apply_poison_db(self, target_pid: str):
        """Marca is_poisoned en la DB para persistencia (si existe RoleAssignment)."""
        rasg = self.r_asgs.get(target_pid)
        if not rasg:
            return
        rasg.is_poisoned = True
        rasg.save()

    def mark_death(self, target_pid: str, killed_by_pid: str, reason: str):
        """Marca la muerte en estado temporal; la aplicamos en DB al final."""
        self.state[target_pid]["will_die"] = True
        self.state[target_pid]["killed_by"] = {"by": killed_by_pid, "reason": reason}
        self.night_events.append({
            "type": "will_die",
            "target": target_pid,
            "by": killed_by_pid,
            "reason": reason
        })

    # ---------------------------
    # Role handlers
    # ---------------------------
    def handle_poisoner(self, actor_pid: str, selection: Dict):
        """Poisoner: envenena al target (target's ability disabled)."""
        if self.is_poisoned(actor_pid):
            # si el Poisoner está envenenado su habilidad falla
            self.private_info[actor_pid].append("Tu habilidad de envenenar ha sido inhabilitada (estás envenenado).")
            return

        targets = selection.get("targets") or []
        if not targets:
            return

        target = targets[0]
        if target not in self.players:
            return

        # aplicar poison (persistente)
        self.apply_poison_db(target)
        self.state[target]["poisoned"] = True
        self.night_events.append({"type":"poison", "actor": actor_pid, "target": target})
        self.private_info[actor_pid].append(f"Has envenenado a {self.players[target].alias}.")

    def handle_imp(self, actor_pid: str, selection: Dict):
        """Imp: intenta matar a target (si target protegido -> no muere, si slayer actúa contrariamente...)."""
        if self.is_poisoned(actor_pid):
            self.private_info[actor_pid].append("Tu habilidad de matar ha sido inhabilitada (estás envenenado).")
            return

        targets = selection.get("targets") or []
        if not targets:
            return

        target = targets[0]
        if target not in self.players or not self.players[target].is_alive:
            return

        # Si target está protegido por Monk u otra protección, fallará
        if self.state[target]["protected"]:
            self.night_events.append({"type":"imp_failed_protected", "actor": actor_pid, "target": target})
            self.private_info[actor_pid].append(f"Tu intento de matar a {self.players[target].alias} ha fallado (estaba protegido).")
            return

        # Marcar muerte
        self.mark_death(target, actor_pid, reason="imp_kill")
        self.night_events.append({"type":"imp_kill", "actor": actor_pid, "target": target})

    def handle_fortune_teller(self, actor_pid: str, selection: Dict):
        """Fortune Teller: tell alignment (simplificado: role.alignment).
           If actor is drunk/poisoned, ability fails.
        """
        if self.is_poisoned(actor_pid):
            self.private_info[actor_pid].append("Tu lectura ha sido inhabilitada (estás envenenado).")
            return

        targets = selection.get("targets") or []
        if not targets:
            return

        target = targets[0]
        if target not in self.players:
            return

        # In the full rules there are red herrings (Spy, Drunk, etc). For now:
        role_name = self.r_asgs[target].role.name
        alignment = self.r_asgs[target].role.alignment
        self.private_info[actor_pid].append(f"La lectura muestra que {self.players[target].alias} tiene alineamiento: {alignment} (rol ~ {role_name}).")
        self.night_events.append({"type":"fortune", "actor":actor_pid, "target":target})

    def handle_undertaker(self, actor_pid: str, selection: Dict):
        """
        Undertaker: learns role of someone who died overnight (BOTC: Undertaker learns the role of the first person who died).
        Implementation: after full night resolution we'll collect deaths and add messages here.
        """
        # mark we need to deliver undertaker info later
        self.state[actor_pid].setdefault("needs_undertaker_info", True)

    def handle_empath(self, actor_pid: str, selection: Dict):
        """
        Empath: learns how many evil players adjacent to them (left/right neighbors).
        We use room.player_order to determine adjacency.
        """
        # guard clauses
        if self.is_poisoned(actor_pid):
            self.private_info[actor_pid].append("Tu habilidad ha sido inhabilitada (estás envenenado).")
            return

        order = self.room.player_order or []
        if not order:
            # fallback: count evil in full table
            evil = sum(1 for pid, rasg in self.r_asgs.items() if rasg.role.alignment in ("minion","demon"))
            self.private_info[actor_pid].append(f"Hay {evil} jugadores malvados en la partida.")
            return

        # find actor position
        try:
            idx = order.index(actor_pid)
        except ValueError:
            # not in order; fallback
            self.private_info[actor_pid].append("No se pudo calcular vecinos.")
            return

        left = order[(idx - 1) % len(order)]
        right = order[(idx + 1) % len(order)]
        cnt = 0
        for neighbor in (left, right):
            rasg = self.r_asgs.get(neighbor)
            if rasg and rasg.role.alignment in ("minion", "demon"):
                cnt += 1
        self.private_info[actor_pid].append(f"Tu Empath detecta {cnt} jugadores malvados entre tus vecinos.")

    def handle_monk(self, actor_pid: str, selection: Dict):
        """
        Monk: protects a player for the night (marks protected flag).
        """
        if self.is_poisoned(actor_pid):
            self.private_info[actor_pid].append("Tu habilidad de protección ha sido inhabilitada (estás envenenado).")
            return

        targets = selection.get("targets") or []
        if not targets:
            return
        target = targets[0]
        if target in self.players:
            self.state[target]["protected"] = True
            self.night_events.append({"type":"monk_protect", "actor": actor_pid, "target": target})
            self.private_info[actor_pid].append(f"Proteges a {self.players[target].alias} esta noche.")

    def handle_ravenkeeper(self, actor_pid: str, selection: Dict):
        """
        Ravenkeeper: if Ravenkeeper dies tonight, they learn the role of someone (implementation: they learn the role of the first person killed).
        We'll defer until we know deaths.
        """
        self.state[actor_pid].setdefault("needs_raven_info", True)

    def handle_slayer(self, actor_pid: str, selection: Dict):
        """
        Slayer: if targets a Demon -> demon dies; else Slayer dies.
        """
        if self.is_poisoned(actor_pid):
            self.private_info[actor_pid].append("Tu habilidad ha sido inhabilitada (estás envenenado).")
            return

        targets = selection.get("targets") or []
        if not targets:
            return
        target = targets[0]
        if target not in self.players:
            return
        target_rasg = self.r_asgs.get(target)
        if target_rasg and target_rasg.role.alignment == "demon":
            # kill demon
            self.mark_death(target, actor_pid, reason="slayer_kill")
            self.night_events.append({"type":"slayer_kill", "actor":actor_pid, "target":target})
            self.private_info[actor_pid].append(f"Has matado al demonio {self.players[target].alias}.")
        else:
            # Slayer dies
            self.mark_death(actor_pid, target, reason="slayer_backfire")
            self.night_events.append({"type":"slayer_backfire", "actor":actor_pid, "target":target})
            self.private_info[actor_pid].append("Tu intento ha fallado y has muerto por la habilidad del Slayer.")

    def handle_spy(self, actor_pid: str, selection: Dict):
        """
        Spy: learns the word or selection of a target or receives extra information.
        Simplified: Spy learns the role name of the target (but real rules are nuanced).
        """
        if self.is_poisoned(actor_pid):
            self.private_info[actor_pid].append("Tu espionaje ha sido inhabilitado (estás envenenado).")
            return
        targets = selection.get("targets") or []
        if not targets:
            return
        target = targets[0]
        if target not in self.players:
            return
        role_name = self.r_asgs[target].role.name
        self.private_info[actor_pid].append(f"Has espiado a {self.players[target].alias}: rol aparente = {role_name}.")
        self.night_events.append({"type":"spy_check", "actor":actor_pid, "target":target})

    def handle_washerwoman(self, actor_pid: str, selection: Dict):
        """
        Washerwoman: learns if a target is a specific role (simplified).
        """
        if self.is_poisoned(actor_pid):
            self.private_info[actor_pid].append("Tu investigación ha sido inhabilitada (estás envenenado).")
            return
        targets = selection.get("targets") or []
        if not targets:
            return
        target = targets[0]
        role_name = self.r_asgs[target].role.name
        self.private_info[actor_pid].append(f"La prueba indica que {self.players[target].alias} podría ser {role_name} (resultado simplificado).")
        self.night_events.append({"type":"washerwoman_check", "actor":actor_pid, "target":target})

    def handle_librarian(self, actor_pid: str, selection: Dict):
        """
        Librarian: simplified to inspecting a role; in full rules returns 'Townsfolk or Minion or Demon' info.
        """
        if self.is_poisoned(actor_pid):
            self.private_info[actor_pid].append("Tu investigación ha sido inhabilitada (estás envenenado).")
            return
        targets = selection.get("targets") or []
        if not targets:
            return
        target = targets[0]
        alignment = self.r_asgs[target].role.alignment
        self.private_info[actor_pid].append(f"Resultado Librarian: {self.players[target].alias} → {alignment}.")
        self.night_events.append({"type":"librarian_check", "actor":actor_pid, "target":target})

    def handle_investigator(self, actor_pid: str, selection: Dict):
        """
        Investigator: simplified detective; returns the role name (in real game returns 'anvil' clues).
        """
        if self.is_poisoned(actor_pid):
            self.private_info[actor_pid].append("Tu investigación ha sido inhabilitada (estás envenenado).")
            return
        targets = selection.get("targets") or []
        if not targets:
            return
        target = targets[0]
        role_name = self.r_asgs[target].role.name
        self.private_info[actor_pid].append(f"Investigator: {self.players[target].alias} → {role_name}.")
        self.night_events.append({"type":"investigator_check", "actor":actor_pid, "target":target})

    def handle_chef(self, actor_pid: str, selection: Dict):
        """
        Chef: gains information about food (simplified: learns if target is evil or not).
        """
        if self.is_poisoned(actor_pid):
            self.private_info[actor_pid].append("Tu habilidad culinaria ha sido inhabilitada (estás envenenado).")
            return
        targets = selection.get("targets") or []
        if not targets:
            return
        target = targets[0]
        alignment = self.r_asgs[target].role.alignment
        self.private_info[actor_pid].append(f"Chef: la comida sugiere que {self.players[target].alias} es {alignment}.")
        self.night_events.append({"type":"chef_check", "actor":actor_pid, "target":target})

    def handle_butler(self, actor_pid: str, selection: Dict):
        """
        Butler: example outsider with first-night/other-night behavior. Simplified to no-op here.
        """
        # For now, we implement no special effect; real behavior can be added later.
        self.private_info[actor_pid].append("Butler: no hay efecto implementado (placeholder).")

    def handle_generic(self, role_name: str, actor_pid: str, selection: Dict):
        """Fallback for roles not explicitly implemented."""
        self.private_info[actor_pid].append(f"No hay handler implementado para {role_name} (acción ignorada).")

    # ---------------------------
    # Main resolver
    # ---------------------------
    def resolve_night(self, selections: Dict[str, Dict], first_night: bool):
        """
        selections: dict player_id -> {"targets": [...], "word": "..." }
        """
        # Get queue from room.active_night_queue (already filtered). If empty, fallback to script logic.
        queue = self.room.active_night_queue or []
        if not queue:
            # fallback: choose first/other nights from script
            raw = self.room.script.night_order
            queue = raw["first_night"] if first_night else raw["other_nights"]

        # iterate roles in order
        for role_name in queue:
            # get actors who have this role
            actors = self.get_player_by_role_name(role_name)
            for actor in actors:
                pid = str(actor.id)
                # skip dead or missing
                if not actor.is_alive:
                    continue

                selection = selections.get(pid, {})
                # check persistent poison that disables ability
                if self.is_poisoned(pid):
                    # actor ability is disabled; still record private info in handlers where needed
                    # many handlers themselves check is_poisoned and append messages
                    pass

                # Dispatch to role handler
                handler_name = f"handle_{role_name.lower().replace(' ', '_')}"
                handler = getattr(self, handler_name, None)
                if handler:
                    try:
                        handler(pid, selection)
                    except Exception as e:
                        logger.exception("Error handling role %s for %s: %s", role_name, pid, e)
                        self.private_info[pid].append(f"Error al ejecutar {role_name}: {e}")
                else:
                    # no direct handler -> generic
                    self.handle_generic(role_name, pid, selection)

        # AFTER all role actions: resolve deaths, undertaker, ravenkeeper, apply DB changes
        deaths = []
        with transaction.atomic():
            # apply deaths
            for pid, st in self.state.items():
                if st.get("will_die"):
                    # re-check protected flag (in case a late effect protected them)
                    if st.get("protected"):
                        # protected -> cancel death
                        self.night_events.append({"type":"protected_survived", "target": pid})
                        continue

                    # apply death in DB
                    player = self.players[pid]
                    player.is_alive = False
                    player.save()
                    deaths.append(pid)
                    self.night_events.append({"type":"death_applied", "target": pid, "killed_by": st.get("killed_by")})

            # Undertaker info: the Undertaker(s) learn the role of the first person who died (if any)
            died_list = deaths.copy()
            if died_list:
                first_dead = died_list[0]
                first_dead_role = None
                rasg = self.r_asgs.get(first_dead)
                if rasg:
                    first_dead_role = rasg.role.name

                for pid, st in self.state.items():
                    if st.get("needs_undertaker_info"):
                        self.private_info[pid].append(f"Undertaker reveals: {self.players[first_dead].alias} was {first_dead_role}.")

                # Ravenkeeper: if Ravenkeeper died, they learn role of someone (we'll give them the first_dead role)
                for pid in died_list:
                    rasg = self.r_asgs.get(pid)
                    if rasg and rasg.role.name == "Ravenkeeper":
                        # Ravenkeeper died; give them info (private)
                        # In practice they'd be dead when receiving this; we still push info for replay
                        for recip_pid in self.private_info.keys():
                            # We assume Ravenkeeper player id is pid — deliver to their private info (they're dead though)
                            # But keep record in private_info map (UI can show it on death screen)
                            self.private_info[pid].append(f"Como Ravenkeeper moriste y ves que {self.players[first_dead].alias} era {first_dead_role}.")

            # persist any other permanent flags (e.g., is_poisoned already set via apply_poison_db)
            # (already applied when Poisoner acted)

        # Return summary
        return {
            "night_events": self.night_events,
            "private_info": self.private_info,
            "deaths": deaths
        }
