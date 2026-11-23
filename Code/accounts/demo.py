"""The open demonstration account the sign-in page names: «почта» 12345, password 12345.

It has the full rights of the head of department and the name drawn in the Figma frames.
It exists while ENABLE_SYNTHETIC_LOGIN is on (the default for the demo stand): every
`migrate` makes sure of it, so a deploy needs no extra step. Turn it off with
ENABLE_SYNTHETIC_LOGIN=0 for a stand with real users.
"""

from django.conf import settings

GUEST = {"username": "12345", "password": "12345", "group": "Head", "name": ("Алексей", "М.")}


def ensure_guest():
    """Create the account (and the role groups) once; an existing account keeps its password."""
    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import Group
    from django.core.management import call_command

    if not getattr(settings, "ENABLE_SYNTHETIC_LOGIN", False):
        return None
    call_command("bootstrap_roles", verbosity=0)
    guest, created = get_user_model().objects.get_or_create(username=GUEST["username"])
    guest.first_name, guest.last_name = GUEST["name"]
    if created:
        guest.set_password(GUEST["password"])
    guest.save()
    guest.groups.set([Group.objects.get(name=GUEST["group"])])
    return guest


def after_migrate(sender, **kwargs):
    # the role permissions belong to the «cases» app: act once they exist
    if sender.label == "cases":
        ensure_guest()
