# 环节：Agent 团队运行层；用途：管理团队循环、任务状态、共享证据、消息或工具。
"""Capability-limited tools. All mutations live in the checkpointed run state."""

from datetime import datetime
from itertools import pairwise

from app.context.service import evaluator_context
from app.domain.models import MESSAGE_TYPES, EvidenceInput, FindingInput, now, uid
from app.rubrics.payload import metric_payload
from app.team.state import active_findings, event, pending_messages, task

TOOL_HELP = {
    "read_skill": "{} -> all assigned Skill specs and instructions; mandatory before scoring",
    "get_dialogue": "{} -> original current messages, observation completeness, service events",
    "get_evidence": "{evidence_ids?: string[]} -> original verified evidence records",
    "share_evidence": "{message_id,speaker,quote,related_indicators:string[]} -> evidence_id",
    "search_knowledge": "{query:string,metric_ids?:string[]} -> versioned local Skill knowledge",
    "get_session_context": "{} -> visit routing, no historic scores",
    "get_previous_evaluations": "{metric_id:string,reason:string} -> historical FACTS only, if Skill allows",
    "time_calculator": "{} -> first-response seconds and adjacent patient/doctor intervals",
    "send_message": "{receiver, message_type, content, evidence_ids?:[], related_indicators?:[]}",
    "get_messages": "{} -> pending/delivered messages; sets DELIVERED",
    "acknowledge_message": "{message_id,disposition:used|irrelevant|answered,reason} -> PROCESSED",
    "request_review": "{metric_ids:string[],reason:string} -> independent temporary reviewer",
    "submit_review": "{decision:uphold|revise|unresolved,reason,evidence_ids:string[]} reviewer only",
    "submit_evaluation": "{findings:FindingInput[],complete?:boolean} -> submit/revise owned metrics; complete=true finishes if all metrics and messages handled",
    "wait": "{} -> wait for another agent; finish when all metrics covered and inbox handled",
    "finish": "{} -> complete only if all assigned metrics submitted and all messages processed",
}


class TeamTools:
    def __init__(self, settings, knowledge):
        self.settings = settings
        self.knowledge = knowledge

    def add_review(self, state, conflict):
        team = state["team"]
        if conflict.get("reviewer"):
            return conflict["reviewer"]
        if team["reviews_created"] >= self.settings.max_reviews:
            conflict["status"] = "UNRESOLVED"
            conflict["reason"] = "review_budget_exhausted"
            return None
        agent = "reviewer:" + conflict["conflict_id"]
        team["tasks"][agent] = task(
            agent, "review", conflict["metric_ids"], "reviewer", conflict["conflict_id"]
        )
        team["tasks"][agent]["evaluation_run_id"] = state["run_id"]
        team["reviews_created"] += 1
        conflict["reviewer"] = agent
        event(
            team,
            "team_lead",
            "create_reviewer",
            {"agent": agent, "conflict_id": conflict["conflict_id"]},
        )
        return agent

    def send(self, state, sender, args):
        team = state["team"]
        receiver = args["receiver"]
        if receiver not in team["tasks"] or receiver == sender:
            raise ValueError("Unknown/self message receiver")
        if args["message_type"] not in MESSAGE_TYPES:
            raise ValueError("Unknown message type")
        if len(team["messages"]) >= self.settings.max_messages:
            raise ValueError("message_budget_exhausted")
        if not isinstance(args.get("content"), str) or not 0 < len(args["content"]) <= 3000:
            raise ValueError("Message content must be 1..3000 characters")
        self.check_evidence(team, args.get("evidence_ids", []))
        if any(m not in state["skills"]["metrics"] for m in args.get("related_indicators", [])):
            raise ValueError("Unknown related metric")
        message = {
            "message_id": uid("msg"),
            "evaluation_run_id": state["run_id"],
            "sender": sender,
            "receiver": receiver,
            "message_type": args["message_type"],
            "evidence_ids": args.get("evidence_ids", []),
            "related_indicators": args.get("related_indicators", []),
            "content": args["content"],
            "status": "PENDING",
            "created_at": now(),
        }
        team["messages"].append(message)
        target = team["tasks"][receiver]
        if target["status"] != "FAILED":
            target["status"] = "PENDING"  # Reopen completed/waiting recipients.
        if args["message_type"] == "RISK_ALERT":
            if not message["evidence_ids"]:
                team["messages"].pop()
                raise ValueError("Risk alerts require source evidence")
            team["risk_alerts"].append({**message, "severity": "serious_service_risk"})
        if args["message_type"] in {"CONFLICT_REPORT", "REVIEW_REQUEST"}:
            self.request_review(
                state,
                sender,
                {"metric_ids": message["related_indicators"], "reason": message["content"]},
            )
        return message

    @staticmethod
    def check_evidence(team, evidence_ids):
        if not isinstance(evidence_ids, list) or any(
            e not in team["evidence"] for e in evidence_ids
        ):
            raise ValueError("Unknown evidence reference")

    def request_review(self, state, sender, args):
        ids = args["metric_ids"]
        if not ids or any(mid not in state["skills"]["metrics"] for mid in ids):
            raise ValueError("Review needs known metric IDs")
        if not args.get("reason"):
            raise ValueError("Review reason required")
        team = state["team"]
        for c in team["conflicts"].values():
            if set(c["metric_ids"]) == set(ids) and c["status"] == "OPEN":
                return {"conflict_id": c["conflict_id"], "reviewer": c.get("reviewer")}
        cid = uid("conflict")
        conflict = {
            "conflict_id": cid,
            "signature": cid,
            "metric_ids": ids,
            "description": str(args["reason"])[:3000],
            "status": "OPEN",
            "review": None,
            "kind": "agent_report",
            "reported_by": sender,
            "finding_ids": [
                active_findings(team)[m]["finding_id"] for m in ids if m in active_findings(team)
            ],
        }
        team["conflicts"][cid] = conflict
        return {"conflict_id": cid, "reviewer": self.add_review(state, conflict)}

    async def execute(self, state, agent, name, args):
        team, session = state["team"], state["session"]
        current = team["tasks"][agent]
        metrics = state["skills"]["metrics"]
        if name == "read_skill":
            current["skills_read"] = True
            return {mid: metric_payload(metrics[mid]) for mid in current["metric_ids"]}
        if name == "get_dialogue":
            return {
                "messages": session["messages"],
                "service_context": session["service_context"],
                "observation_complete": session["observation_complete"],
            }
        if name == "get_session_context":
            return evaluator_context(state["context"])
        if name == "get_previous_evaluations":
            mid = args["metric_id"]
            if mid not in current["metric_ids"] or not args.get("reason"):
                raise ValueError("History must be justified for an assigned metric")
            if "historical_dialogue" not in metrics[mid]["evidence"]["allowed_sources"]:
                return {"status": "not_allowed_by_skill", "records": []}
            return {
                "status": state["context"]["history_status"],
                "records": [
                    {
                        "session_id": h["session"]["session_id"],
                        "session_time": h["session"]["session_time"],
                        "messages": h["session"]["messages"],
                    }
                    for h in state["context"]["history"][:5]
                ],
            }
        if name == "search_knowledge":
            return await self.knowledge.search(
                str(args.get("query", ""))[:200], args.get("metric_ids", current["metric_ids"])
            )
        if name == "time_calculator":
            result = self.time_facts(session)
            current["time_facts"] = result
            return result
        if name == "share_evidence":
            evidence = EvidenceInput.model_validate(
                {k: args[k] for k in ("message_id", "speaker", "quote")}
            )
            message = next(
                (m for m in session["messages"] if m["message_id"] == evidence.message_id), None
            )
            if (
                not message
                or message["role"] != evidence.speaker
                or message["message_kind"] != "dialogue"
                or evidence.speaker == "system"
            ):
                raise ValueError("Evidence speaker/source mismatch")
            if evidence.quote not in message["content"] or message["modality"] != "text":
                raise ValueError("Evidence must be a contiguous original text quote")
            related = args.get("related_indicators", [])
            if any(mid not in metrics for mid in related):
                raise ValueError("Unknown evidence metric")
            for item in team["evidence"].values():
                if (
                    item["message_id"] == evidence.message_id
                    and item["original_text"] == evidence.quote
                ):
                    item["related_indicators"] = sorted(set(item["related_indicators"] + related))
                    return item
            item = {
                "evidence_id": uid("evidence"),
                "session_id": session["session_id"],
                "message_id": evidence.message_id,
                "turn_id": message["sequence"],
                "speaker": evidence.speaker,
                "original_text": evidence.quote,
                "source_agent": agent,
                "related_indicators": related,
                "created_at": now(),
            }
            team["evidence"][item["evidence_id"]] = item
            return item
        if name == "get_evidence":
            ids = args.get("evidence_ids", list(team["evidence"]))
            self.check_evidence(team, ids)
            return [team["evidence"][eid] for eid in ids]
        if name == "send_message":
            return self.send(state, agent, args)
        if name == "get_messages":
            messages = pending_messages(team, agent)
            for m in messages:
                m["status"] = "DELIVERED"
            return messages
        if name == "acknowledge_message":
            message = next(
                (m for m in team["messages"] if m["message_id"] == args["message_id"]), None
            )
            if not message or message["receiver"] != agent or message["status"] != "DELIVERED":
                raise ValueError("Read your message before acknowledging it")
            if args.get("disposition") not in {"used", "irrelevant", "answered"} or not args.get(
                "reason"
            ):
                raise ValueError("Message processing disposition and reason required")
            message.update(
                status="PROCESSED",
                disposition=args["disposition"],
                processing_reason=str(args["reason"])[:2000],
                processed_at=now(),
            )
            return message
        if name == "request_review":
            return self.request_review(state, agent, args)
        if name == "submit_review":
            if current["kind"] != "reviewer" or not current["skills_read"]:
                raise ValueError(
                    "Only an independent reviewer with loaded Skills may submit review"
                )
            if args.get("decision") not in {"uphold", "revise", "unresolved"} or not args.get(
                "reason"
            ):
                raise ValueError("Invalid review decision")
            self.check_evidence(team, args.get("evidence_ids", []))
            if args["decision"] != "unresolved" and not args.get("evidence_ids"):
                raise ValueError("Review resolution needs original evidence")
            conflict = team["conflicts"][current["conflict_id"]]
            conflict["review"] = {"reviewer": agent, **args, "created_at": now()}
            if args["decision"] == "unresolved":
                conflict["status"] = "UNRESOLVED"
            for receiver, owned in list(team["tasks"].items()):
                if owned["kind"] != "evaluator" or not set(owned["metric_ids"]) & set(
                    conflict["metric_ids"]
                ):
                    continue
                self.send(
                    state,
                    agent,
                    {
                        "receiver": receiver,
                        "message_type": "CLARIFICATION_REQUEST",
                        "content": f"Independent review ({args['decision']}): {args['reason']}",
                        "evidence_ids": args.get("evidence_ids", []),
                        "related_indicators": conflict["metric_ids"],
                    },
                )
            current["status"] = "COMPLETED"
            return {"status": "review_submitted", "score_override": False}
        if name == "submit_evaluation":
            return self.submit(state, agent, args)
        if name == "wait":
            current["status"] = "WAITING"
            return {"status": "WAITING"}
        if name == "finish":
            if current["kind"] == "reviewer":
                raise ValueError("Reviewer must submit_review")
            if set(current["findings"]) != set(current["metric_ids"]) or pending_messages(
                team, agent
            ):
                raise ValueError("Required metrics or incoming messages remain unfinished")
            current["status"] = "COMPLETED"
            return {"status": "COMPLETED"}
        raise ValueError("Unknown tool")

    def submit(self, state, agent, args):
        team, metrics = state["team"], state["skills"]["metrics"]
        current = team["tasks"][agent]
        if current["kind"] != "evaluator" or not current["skills_read"]:
            raise ValueError("Only assigned evaluators with loaded Skills may submit scores")
        items = [FindingInput.model_validate(f) for f in args["findings"]]
        if not items or len({f.metric_id for f in items}) != len(items):
            raise ValueError("Empty/duplicate metric submissions")
        prepared = []
        for f in items:
            if f.metric_id not in current["metric_ids"]:
                raise ValueError("Cannot modify another evaluator's score")
            spec = metrics[f.metric_id]
            self.check_evidence(team, f.evidence_ids)
            if f.risk != "none" and not f.evidence_ids:
                raise ValueError("Risk flag requires original evidence")
            for claim in f.claims:
                self.check_evidence(team, claim.evidence_ids)
                # 将已经通过引用约束的 claim 证据归并到 Finding，供计分输入检查使用。
                f.evidence_ids = list(dict.fromkeys(f.evidence_ids + claim.evidence_ids))
                if claim.polarity == "absent" and not state["session"]["observation_complete"]:
                    raise ValueError("Absence claim requires complete observation")
            if any(
                rule not in {r["rule_id"] for r in spec["manual_review"]}
                for rule in f.review_rule_ids
            ):
                raise ValueError("Unknown manual review rule")
            if spec["status"] == "published" and "rubric_unpublished" in f.review_rule_ids:
                raise ValueError(
                    "metric.yaml status is published: rubric_unpublished does not apply"
                )
            if f.score is not None:
                if spec["status"] != "published" or spec["configuration_issues"]:
                    raise ValueError("Skill not published consistently; submit NOT_EVALUABLE")
                if f.score not in spec["score_values"] or not f.evidence_ids or not f.claims:
                    raise ValueError("Score needs a Skill anchor and source-grounded claims")
                if f.review_rule_ids:
                    raise ValueError("Unresolved review rules cannot carry a score")
                if "time_calculator" in spec.get("required_tools", []) and not current.get(
                    "time_facts", {}
                ).get("available"):
                    raise ValueError("Required reliable time facts missing")
            prior = current["findings"].get(f.metric_id)
            revision = prior["revision_count"] + 1 if prior else 0
            if revision > self.settings.max_revisions:
                raise ValueError("revision_budget_exhausted")
            finding = {
                **f.model_dump(),
                "finding_id": uid("finding"),
                "agent_id": agent,
                "dimension_id": spec["dimension_id"],
                "metric_version": spec["version"],
                "revision_count": revision,
                "supersedes_finding_id": prior["finding_id"] if prior else None,
            }
            prepared.append(finding)
        for finding in prepared:
            current["findings"][finding["metric_id"]] = finding
            team["finding_history"].append(finding.copy())
            if finding["risk"] == "serious_service_risk":
                team["risk_alerts"].append(
                    {
                        "source_agent": agent,
                        "severity": finding["risk"],
                        "metric_id": finding["metric_id"],
                        "evidence_ids": finding["evidence_ids"],
                        "reason": finding["reason"],
                        "created_at": now(),
                    }
                )
        if (
            args.get("complete") is True
            and set(current["findings"]) == set(current["metric_ids"])
            and not pending_messages(team, agent)
        ):
            current["status"] = "COMPLETED"
        return {
            "accepted": [f["metric_id"] for f in prepared],
            "next": "Process messages, then finish or continue autonomous investigation",
        }

    @staticmethod
    def time_facts(session):
        dialogue = [
            m
            for m in session["messages"]
            if m["message_kind"] == "dialogue" and m["modality"] == "text"
        ]
        first = next((m for m in dialogue if m["role"] == "doctor" and m["content"].strip()), None)
        context = session.get("service_context", {})
        start = context.get("consultation_started_at")
        seconds = None
        try:
            if (
                first
                and first["timestamp"]
                and start
                and context.get("start_basis") == "order_timestamp"
            ):
                origin = datetime.fromisoformat(start)
                if origin.utcoffset() is not None:
                    seconds = (datetime.fromisoformat(first["timestamp"]) - origin).total_seconds()
        except (ValueError, TypeError):
            pass
        pairs = []
        for left, right in pairwise(dialogue):
            if (
                left["role"] == "patient"
                and right["role"] == "doctor"
                and left["timestamp"]
                and right["timestamp"]
            ):
                interval = (
                    datetime.fromisoformat(right["timestamp"])
                    - datetime.fromisoformat(left["timestamp"])
                ).total_seconds()
                if interval >= 0:
                    pairs.append(
                        {
                            "patient_message": left["message_id"],
                            "doctor_message": right["message_id"],
                            "seconds": interval,
                        }
                    )
        return {
            "available": seconds is not None and seconds >= 0,
            "first_response_seconds": seconds if seconds is not None and seconds >= 0 else None,
            "adjacent_response_intervals": pairs,
            "limitation": "Adjacent intervals do not prove semantic question/answer pairing",
        }
