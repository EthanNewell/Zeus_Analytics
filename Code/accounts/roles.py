"""The one registry of roles: group name, label shown in the interface, exact permissions."""

from dataclasses import dataclass

SPECIALIST_PERMISSIONS = (
    "view_case",
    "view_evidence",
    "add_evidence",
    "view_review",
    "add_review",
)


@dataclass(frozen=True)
class Role:
    group: str
    label: str
    duties: str
    permissions: tuple[str, ...]


ROLES = (
    Role(
        "Specialist",
        "Специалист",
        "Смотрит реестр и карточки, фиксирует результат своей проверки.",
        SPECIALIST_PERMISSIONS,
    ),
    Role(
        "Controller",
        "Проверяющий",
        "Дополнительно загружает таблицы и запускает анализ.",
        SPECIALIST_PERMISSIONS + ("import_cases", "run_analysis"),
    ),
    Role(
        "Head",
        "Руководитель",
        "Видит всё и выгружает результаты проверки в CSV.",
        SPECIALIST_PERMISSIONS + ("import_cases", "run_analysis", "export_cases"),
    ),
)


def role_label(user):
    if user.is_superuser:
        return "Администратор"
    groups = set(user.groups.values_list("name", flat=True))
    for role in reversed(ROLES):
        if role.group in groups:
            return role.label
    return ""
