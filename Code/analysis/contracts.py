from enum import StrEnum


class RuleStatus(StrEnum):
    TRIGGERED = "triggered"
    NOT_TRIGGERED = "not_triggered"
    INSUFFICIENT_DATA = "insufficient_data"
    NOT_APPLICABLE = "not_applicable"


class Priority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
