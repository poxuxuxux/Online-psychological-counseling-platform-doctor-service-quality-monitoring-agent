# 环节：后端应用入口层；用途：提供应用启动、配置、命令行或合成演示能力。
"""Small synthetic initial/follow-up examples; never read private local datasets."""

from app.domain.models import Session


def sessions():
    output = []
    for index in range(3):
        date = f"2026-10-{10 + index * 3:02d}"
        dialogue = [
            (
                "patient",
                "最近总睡不好，白天也很累。"
                if index == 0
                else "我按上次说的记录了睡眠，但还是担心。",
            ),
            ("doctor", "听起来睡眠问题让你很辛苦。可以说说持续多久、通常几点入睡吗？"),
            ("patient", "大概两周，最近工作压力大。"),
            (
                "doctor",
                "我们先一起了解睡眠和压力的关系。你愿意继续记录一周入睡和醒来时间，下次一起看看吗？",
            ),
        ]
        output.append(
            Session.model_validate(
                {
                    "session_id": f"demo-team-{index + 1}",
                    "source_id": "synthetic-demo",
                    "patient_id": "synthetic-patient-1",
                    "doctor_id": "synthetic-doctor-1",
                    "anonymized_patient_ref": "synthetic-patient-1",
                    "history_complete": True,
                    "observation_complete": True,
                    "session_time": date + "T10:00:00+08:00",
                    "imported_at": date + "T11:00:00+08:00",
                    "service_context": {
                        "consultation_started_at": date + "T10:00:00+08:00",
                        "start_basis": "order_timestamp",
                        "observation_complete": True,
                    },
                    "messages": [
                        {
                            "message_id": f"m{n}",
                            "sequence": n,
                            "role": role,
                            "content": content,
                            "timestamp": date + f"T10:0{n}:00+08:00",
                        }
                        for n, (role, content) in enumerate(dialogue)
                    ],
                }
            )
        )
    return output
