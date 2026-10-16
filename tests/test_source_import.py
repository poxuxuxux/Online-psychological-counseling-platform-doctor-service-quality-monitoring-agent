import json
from datetime import UTC, datetime

import pytest
from ijson.common import JSONError

from app.application.preprocessing.rounds import first_response, interaction_interval, split_rounds
from app.cli import preview
from app.infrastructure.importers.hxq_json import iter_threads, normalize_thread


def msg(mid, time, role="patient", kind="dialogue", text="合成问题", order="a", obj="RC:TxtMsg"):
    return {
        "message_id": mid,
        "create_time": "2024-05-29 " + time,
        "role": role,
        "message_kind": kind,
        "content": {"content": text},
        "order_no": order,
        "object_name": obj,
    }


def normalize(rows):
    return normalize_thread({"chat_session_id": "synthetic-thread", "messages": rows}, "fixture")


def purchase(mid="1", time="12:50:39", order="a"):
    return msg(mid, time, kind="system_notification", text="已购买图文问诊服务", order=order)


def test_first_response_ignores_doctor_system_notification():
    rows = normalize(
        [
            purchase(),
            msg("2", "13:37:38", "doctor", "system_notification", "您购买的图文咨询医生已接诊"),
            msg("3", "13:41:24", "doctor", text="你好"),
        ]
    )
    timing = first_response(split_rounds(rows, "t")[0])
    assert timing.seconds == 3045
    assert timing.reply_message_id == rows[2].message_id


def test_explicit_orders_are_separated_and_missing_order_not_guessed():
    rounds = split_rounds(
        normalize([purchase(), purchase("2", order="b"), msg("3", "13:00:00", order=None)]), "t"
    )
    assert len(rounds) == 3
    assert "missing_order" in rounds[2].issues


def test_withdrawal_keeps_following_dialogue_but_flags_interval():
    rows = normalize(
        [
            purchase(time="20:04:24"),
            msg("2", "21:25:03", "doctor", "system_notification", "医生已退诊"),
            msg("3", "21:25:16", "doctor"),
        ]
    )
    timing = first_response(split_rounds(rows, "t")[0])
    assert timing.seconds == 4852
    assert timing.issues == ("withdrawn_order",)


def test_media_before_text_prevents_false_first_reply():
    rows = normalize(
        [purchase(), msg("2", "13:00:00", "doctor", obj="RC:VcMsg"), msg("3", "13:10:00", "doctor")]
    )
    timing = first_response(split_rounds(rows, "t")[0])
    assert timing.seconds is None
    assert timing.issues == ("earlier_unparsed_doctor_response",)


def test_seconds_and_milliseconds_agree_and_conflict_blocks_timing():
    row = purchase()
    seconds = datetime(2024, 5, 29, 4, 50, 39, tzinfo=UTC).timestamp()
    for multiplier in (1, 1000):
        row["msg_timestamp"] = seconds * multiplier
        assert normalize([row])[0].issues == ()
    row["msg_timestamp"] = (seconds + 300) * 1000
    normalized = normalize([row])[0]
    assert normalized.timestamp is None
    assert "timestamp_conflict" in normalized.issues


def test_duplicate_messages_fail_and_identity_is_namespaced():
    with pytest.raises(ValueError, match="Duplicate"):
        normalize([purchase(), purchase()])
    a = normalize([purchase()])[0]
    b = normalize_thread({"chat_session_id": "other", "messages": [purchase()]}, "fixture")[0]
    assert a.message_id != b.message_id


def test_repeated_purchase_at_different_time_requires_review():
    rounds = split_rounds(normalize([purchase(), purchase("2", "14:00:00")]), "t")
    assert "multiple_purchase_boundaries" in rounds[0].issues
    assert first_response(rounds[0]).seconds is None


def test_explicit_pair_must_be_inside_same_round_and_in_time_order():
    rows = normalize([msg("1", "13:42:10"), msg("2", "13:42:25", "doctor")])
    round_ = split_rounds(rows, "t")[0]
    assert interaction_interval(round_, rows[0].message_id, rows[1].message_id).seconds == 15
    assert interaction_interval(round_, "foreign", rows[1].message_id).seconds is None


def test_streaming_import_accepts_whitespace_and_preview_omits_text(tmp_path):
    path = tmp_path / "source.json"
    path.write_text(
        json.dumps(
            {
                "data": [
                    {
                        "chat_session_id": "private-id",
                        "messages": [
                            purchase(),
                            msg("2", "13:00:00", "doctor", text="PRIVATE_SYNTHETIC_SENTINEL"),
                        ],
                    }
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    assert len(list(iter_threads(path))) == 1
    output = json.dumps(preview(path, 0, "Asia/Shanghai"))
    assert "PRIVATE_SYNTHETIC_SENTINEL" not in output
    assert "private-id" not in output


@pytest.mark.parametrize("content", ["{}", '{"data": [', '{"data": [5]}'])
def test_bad_source_fails(tmp_path, content):
    path = tmp_path / "bad.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises((ValueError, TypeError, JSONError)):
        list(iter_threads(path))
