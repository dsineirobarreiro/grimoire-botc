from django.db import migrations


def load_trouble_brewing(apps, schema_editor):
    Role = apps.get_model("game", "Role")
    Script = apps.get_model("game", "Script")

    # ----------------------------------------------------
    # 1. Roles de Trouble Brewing
    # ----------------------------------------------------
    tb_roles_data = [
        # Townsfolk
        ("Washerwoman", "townsfolk", True, False, False, True),
        ("Librarian", "townsfolk", True, False, False, True),
        ("Investigator", "townsfolk", True, False, False, True),
        ("Chef", "townsfolk", True, True, False, False),
        ("Empath", "townsfolk", True, True, False, False),
        ("Fortune Teller", "townsfolk", True, True, False, True),
        ("Undertaker", "townsfolk", False, True, False, False),
        ("Monk", "townsfolk", False, True, False, True),
        ("Ravenkeeper", "townsfolk", False, False, False, False),
        ("Virgin", "townsfolk", False, False, False, True),
        ("Slayer", "townsfolk", False, False, True, True),
        ("Soldier", "townsfolk", False, False, False, False),
        ("Mayor", "townsfolk", False, False, False, False),

        # Outsiders
        ("Butler", "outsider", True, True, False, True),
        ("Drunk", "outsider", False, False, False, False),
        ("Recluse", "outsider", False, False, False, False),
        ("Saint", "outsider", False, False, False, True),

        # Minions
        ("Poisoner", "minion", True, True, False, True),
        ("Spy", "minion", True, True, False, False),
        ("Scarlet Woman", "minion", False, True, False, False),
        ("Baron", "minion", False, False, False, False),

        # Demon
        ("Imp", "demon", True, True, False, True),
    ]

    role_objects = {}

    for name, alignment, first_night, other_night, is_once, requires_target in tb_roles_data:
        role = Role.objects.create(
            name=name,
            alignment=alignment,
            first_night=first_night,
            other_night=other_night,
            is_once_per_trouble_brewing=is_once,
            requires_target=requires_target,
        )
        role_objects[name] = role

    # ----------------------------------------------------
    # 2. Night Order (según la hoja oficial)
    # ----------------------------------------------------
    night_order = {
        "first_night": [
            "Poisoner",
            "Washerwoman",
            "Librarian",
            "Investigator",
            "Chef",
            "Empath",
            "Fortune Teller",
            "Butler",
            "Spy"
        ],
        "other_nights": [
            "Poisoner",
            "Monk",
            "Imp",
            "Empath",
            "Fortune Teller"
        ]
    }

    # ----------------------------------------------------
    # 3. Crear Script Trouble Brewing
    # ----------------------------------------------------
    tb = Script.objects.create(
        name="Trouble Brewing",
        night_order=night_order
    )

    # Asignar roles al script
    tb.roles.set(role_objects.values())


def undo_trouble_brewing(apps, schema_editor):
    Role = apps.get_model("game", "Role")
    Script = apps.get_model("game", "Script")

    Script.objects.filter(name="Trouble Brewing").delete()

    trouble_brewing_role_names = [
        "Washerwoman", "Librarian", "Investigator", "Chef", "Empath",
        "Fortune Teller", "Undertaker", "Monk", "Ravenkeeper", "Virgin",
        "Slayer", "Mayor", "Soldier", "Butler", "Drunk", "Recluse", "Saint",
        "Poisoner", "Spy", "Scarlet Woman", "Baron", "Imp"
    ]

    Role.objects.filter(name__in=trouble_brewing_role_names).delete()


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.RunPython(load_trouble_brewing, undo_trouble_brewing),
    ]
