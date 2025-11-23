import uuid
from django.db import models

from game.utils import generate_room_code


# ---------------------------------------------------------
# ROLE (STATIC)
# ---------------------------------------------------------
class Role(models.Model):
    ALIGNMENTS = [
        ("townsfolk", "Townsfolk"),
        ("outsider", "Outsider"),
        ("minion", "Minion"),
        ("demon", "Demon"),
        ("traveller", "Traveller"),
    ]

    name = models.CharField(max_length=100, unique=True)
    alignment = models.CharField(max_length=20, choices=ALIGNMENTS)

    image_path = models.CharField(max_length=128, blank=True)

    # Useful metadata for engine
    first_night = models.BooleanField(default=False)
    other_night = models.BooleanField(default=False)
    is_once_per_game = models.BooleanField(default=False)
    requires_target = models.BooleanField(default=False)

    # Optional priority within a night (explicit override)
    night_priority = models.IntegerField(null=True, blank=True)

    @property
    def image_url(self):
        from django.templatetags.static import static
        return static(self.image_path)

    def __str__(self):
        return f"{self.name} ({self.alignment})"


# ---------------------------------------------------------
# SCRIPT (STATIC)
# ---------------------------------------------------------
class Script(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    name = models.CharField(max_length=100, unique=True)

    # All roles that exist in this script
    roles = models.ManyToManyField(Role, related_name="scripts")

    # Night order defined by script (list of role names)
    night_order = models.JSONField(default=dict)

    def __str__(self):
        return self.name


# ---------------------------------------------------------
# ROOM (GAME INSTANCE)
# ---------------------------------------------------------
class Room(models.Model):
    GAME_STATES = [
        ("WAITING", "Waiting for players"),
        ("ASSIGNING_ROLES", "Assigning roles"),
        ("ROLE", "Showing roles"),
        ("FIRST_NIGHT", "First night"),
        ("NIGHT", "Night"),
        ("DAY_DISCUSSION", "Day discussion"),
        ("NOMINATION", "Nomination phase"),
        ("VOTING", "Voting phase"),
        ("NIGHT_RESULTS", "Night result reveal"),
        ("GAME_END", "Game end"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=6, unique=True, blank=True)

    script = models.ForeignKey(Script, on_delete=models.PROTECT)

    state = models.CharField(
        max_length=30, choices=GAME_STATES, default="WAITING"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    current_day = models.IntegerField(default=1)
    current_night = models.IntegerField(default=1)

    # Final filtered night queue for the specific game
    active_night_queue = models.JSONField(default=list)

    # For the "circle" ordering in voting
    player_order = models.JSONField(default=list)
    
    def save(self, *args, **kwargs):
        if not self.code:
            self.code = self._generate_unique_code()
        super().save(*args, **kwargs)
    
    def _generate_unique_code(self):
        code = generate_room_code()
        while Room.objects.filter(code=code).exists():
            code = generate_room_code()
        return code

    def __str__(self):
        return f"Room {self.id} ({self.script.name})"


# ---------------------------------------------------------
# PLAYER
# ---------------------------------------------------------
class Player(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="players")

    # If you want to allow anonymous play, you can use char field instead
    # user = models.ForeignKey(
    #    User, null=True, blank=True, on_delete=models.SET_NULL
    #)

    alias = models.CharField(max_length=50)
    photo_url = models.URLField(null=True, blank=True)

    is_alive = models.BooleanField(default=True)
    is_ready = models.BooleanField(default=False)

    # Needed for WebSocket individual channel
    socket_id = models.CharField(max_length=255, null=True, blank=True)

    # Used for BOTC-style voting
    last_vote_toggle = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.alias} in {self.room.id}"


# ---------------------------------------------------------
# ROLE ASSIGNMENT
# ---------------------------------------------------------
class RoleAssignment(models.Model):
    player = models.OneToOneField(Player, on_delete=models.CASCADE, related_name="role_assignment")
    role = models.ForeignKey(Role, on_delete=models.PROTECT)

    # If this player is drunk, what role they *think* they have
    drunk_real_role = models.ForeignKey(
        Role,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="drunk_players"
    )

    is_poisoned = models.BooleanField(default=False)
    is_red_herring = models.BooleanField(default=False)
    died_at_night = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.player.alias} → {self.role.name}"


# ---------------------------------------------------------
# NOMINATION (DAY PHASE)
# ---------------------------------------------------------
class Nomination(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE)

    nominator = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="nominations_made")
    nominee = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="nominations_received")

    created_at = models.DateTimeField(auto_now_add=True)

    # Both must confirm before voting phase starts
    nominator_confirmed = models.BooleanField(default=False)
    nominee_confirmed = models.BooleanField(default=False)

    # After vote resolution
    votes_for = models.IntegerField(default=0)
    executed = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.nominator.alias} nominates {self.nominee.alias}"


# ---------------------------------------------------------
# VOTE
# ---------------------------------------------------------
class Vote(models.Model):
    nomination = models.ForeignKey(Nomination, on_delete=models.CASCADE, related_name="votes")
    player = models.ForeignKey(Player, on_delete=models.CASCADE)

    timestamp = models.DateTimeField(auto_now_add=True)
    voted = models.BooleanField()

    def __str__(self):
        return f"{self.player.alias} voted {self.voted}"

# ---------------------------------------------------------
# NIGHT ACTION
# ---------------------------------------------------------
class NightAction(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE)
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    selection = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
