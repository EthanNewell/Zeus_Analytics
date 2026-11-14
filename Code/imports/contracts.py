from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class ImportError:
    row: int
    field: str
    code: str
    message: str


@dataclass(frozen=True)
class ImportResult:
    batch_id: UUID | None
    case_ids: tuple[UUID, ...] = ()
    errors: tuple[ImportError, ...] = ()

    def __post_init__(self):
        if self.errors and (self.case_ids or self.batch_id is not None):
            raise ValueError("A failed import cannot return saved domain records")
