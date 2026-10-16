"""Conservative order grouping and evidence-linked timing, with no service scores."""

from app.domain.source_data import ResponseTiming, SourceMessage, SourceRound
from app.infrastructure.importers.hxq_json import stable_ref


def split_rounds(messages: list[SourceMessage], thread_ref: str) -> list[SourceRound]:
    """Only explicit order associations are trusted in v1; missing orders stay unresolved."""
    rounds: dict[str, SourceRound] = {}
    for message in messages:
        key = (
            stable_ref(thread_ref, "order", message.order_ref)
            if message.order_ref
            else stable_ref(thread_ref, "unassigned", message.message_id)
        )
        if key not in rounds:
            rounds[key] = SourceRound(key)
        current = rounds[key]
        current.messages.append(message)
        if not message.order_ref and "missing_order" not in current.issues:
            current.issues.append("missing_order")
        for issue in message.issues:
            if issue not in current.issues:
                current.issues.append(issue)
    for current in rounds.values():
        purchases = [m for m in current.messages if m.event == "purchase"]
        if not purchases:
            current.issues.append("missing_purchase_boundary")
        elif len(purchases) > 1:
            times = {m.timestamp for m in purchases}
            if len(times) > 1 or None in times:
                current.issues.append("multiple_purchase_boundaries")
        if any(m.event == "withdrawn" for m in current.messages):
            current.issues.append("withdrawn_order")
        # Never assert a complete service record simply because the export stops.
        current.issues.append("end_boundary_unconfirmed")
    return list(rounds.values())


def first_response(round_: SourceRound) -> ResponseTiming:
    basis = "purchase_notification_proxy"
    blocking = {
        "missing_order",
        "multiple_purchase_boundaries",
        "timestamp_conflict",
        "missing_timestamp",
        "invalid_numeric_timestamp",
        "invalid_create_time",
        "message_kind_conflict",
    }
    if blocking.intersection(round_.issues):
        return ResponseTiming(None, None, None, basis, tuple(round_.issues))
    messages = sorted(round_.messages, key=lambda m: (m.timestamp, m.sequence))
    starts = [m for m in messages if m.event == "purchase"]
    if not starts:
        return ResponseTiming(None, None, None, basis, ("missing_purchase_boundary",))
    start = starts[0]
    for message in messages:
        if (message.timestamp, message.sequence) < (start.timestamp, start.sequence):
            continue
        if message.role == "doctor" and message.kind == "dialogue":
            if not message.is_doctor_text:
                return ResponseTiming(
                    None,
                    start.message_id,
                    message.message_id,
                    basis,
                    ("earlier_unparsed_doctor_response",),
                )
            seconds = (message.timestamp - start.timestamp).total_seconds()
            issues = ("withdrawn_order",) if "withdrawn_order" in round_.issues else ()
            return ResponseTiming(seconds, start.message_id, message.message_id, basis, issues)
    return ResponseTiming(None, start.message_id, None, basis, ("no_observed_reply",))


def interaction_interval(round_: SourceRound, patient_id: str, doctor_id: str) -> ResponseTiming:
    """Compute an explicitly supplied response pair; semantic matching belongs to an Agent."""
    messages = {m.message_id: m for m in round_.messages}
    patient, doctor = messages.get(patient_id), messages.get(doctor_id)
    if (
        patient is None
        or doctor is None
        or patient.role != "patient"
        or patient.kind != "dialogue"
        or not doctor.is_doctor_text
    ):
        return ResponseTiming(None, patient_id, doctor_id, "explicit_pair", ("invalid_pair",))
    if patient.timestamp is None or doctor.timestamp is None:
        return ResponseTiming(None, patient_id, doctor_id, "explicit_pair", ("missing_timestamp",))
    seconds = (doctor.timestamp - patient.timestamp).total_seconds()
    if seconds < 0:
        return ResponseTiming(None, patient_id, doctor_id, "explicit_pair", ("negative_interval",))
    return ResponseTiming(seconds, patient_id, doctor_id, "explicit_pair")
