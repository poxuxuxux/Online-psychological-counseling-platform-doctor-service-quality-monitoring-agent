"""Local import contracts. These contain raw text and must not be sent to a model."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class SourceMessage:
    message_id: str
    sequence: int
    role: str
    kind: str
    object_name: str
    text: str = field(repr=False)
    timestamp: datetime | None = None
    order_ref: str | None = field(default=None, repr=False)
    event: str | None = None
    issues: tuple[str, ...] = ()

    @property
    def is_doctor_text(self) -> bool:
        return (
            self.role == "doctor"
            and self.kind == "dialogue"
            and self.object_name == "RC:TxtMsg"
            and bool(self.text.strip())
        )


@dataclass
class SourceRound:
    round_id: str
    messages: list[SourceMessage] = field(default_factory=list, repr=False)
    issues: list[str] = field(default_factory=list)
    segmentation_version: str = "orders-v1"


@dataclass(frozen=True)
class ResponseTiming:
    seconds: float | None
    start_message_id: str | None
    reply_message_id: str | None
    basis: str
    issues: tuple[str, ...] = ()
