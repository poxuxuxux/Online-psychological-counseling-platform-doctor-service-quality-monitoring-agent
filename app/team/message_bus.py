# 环节：团队消息总线；用途：持久化中心化消息，区分投递、读取和业务处理，禁止同伴互发。
import copy

from app.domain.models import now, uid
from app.team.state import event

LEADER = "team_lead"


class MessageBus:
    def __init__(self, team, max_messages):
        self.team, self.max_messages = team, max_messages

    def send_message(self, sender, receiver, message_type, payload, *, round_number=0, version=None):
        if (sender == receiver or sender not in self.team["tasks"]
                or receiver not in self.team["tasks"] or LEADER not in {sender, receiver}):
            raise ValueError("Only Leader<->Teammate messages are allowed")
        if len(self.team["messages"]) >= self.max_messages:
            raise ValueError("message_budget_exhausted")
        item = {"message_id": uid("msg"), "evaluation_run_id": self.team["run_id"],
                "sender": sender, "receiver": receiver, "message_type": message_type,
                "payload": copy.deepcopy(payload), "round": round_number,
                "report_version": version, "status": "PENDING", "created_at": now()}
        self.team["messages"].append(item)
        event(self.team, sender, "send_message", {"message_id": item["message_id"],
              "receiver": receiver, "message_type": message_type, "round": round_number,
              "report_version": version})
        return item["message_id"]

    def check_inbox(self, receiver):
        items = [m for m in self.team["messages"] if m["receiver"] == receiver
                 and m["status"] in {"PENDING", "DELIVERED"}]
        for item in items:
            item["status"] = "DELIVERED"
        if items:
            event(self.team, receiver, "check_inbox", {"message_ids": [m["message_id"] for m in items]})
        return copy.deepcopy(items)

    def acknowledge(self, receiver, message_ids, reason):
        for mid in message_ids:
            item = next(m for m in self.team["messages"] if m["message_id"] == mid)
            if item["receiver"] != receiver or item["status"] != "DELIVERED":
                raise ValueError("Only a delivered receiver message can be processed")
            item.update(status="PROCESSED", disposition="handled", processing_reason=reason,
                        processed_at=now())
            event(self.team, receiver, "acknowledge_message", {"message_id": mid, "reason": reason})
