from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class RuleStatus(StrEnum):
    TRIGGERED = "triggered"
    NOT_TRIGGERED = "not_triggered"
    INSUFFICIENT_DATA = "insufficient_data"
    NOT_APPLICABLE = "not_applicable"


class Priority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


@dataclass(frozen=True)
class RuleResult:
    case_id: UUID
    analysis_run_id: UUID
    rule_code: str
    rule_version: str
    status: RuleStatus
    priority: Priority
    explanation: str
    used_fact_ids: tuple[UUID, ...] = ()
    evidence_ids: tuple[UUID, ...] = ()
    missing_fields: tuple[str, ...] = ()
    is_demonstration: bool = False

    def __post_init__(self):
        if not isinstance(self.status, RuleStatus) or not isinstance(self.priority, Priority):
            raise ValueError("Use RuleStatus and Priority enum values")
        if (
            not self.rule_code.strip()
            or not self.rule_version.strip()
            or not self.explanation.strip()
        ):
            raise ValueError("Rule code, version and explanation are required")
        if self.status == RuleStatus.INSUFFICIENT_DATA and not self.missing_fields:
            raise ValueError("An incomplete result must identify missing fields")
