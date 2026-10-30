# 环节：Agent 团队运行层；用途：管理团队循环、任务状态、共享证据、消息或工具。
"""Capability-limited tools. All mutations live in the checkpointed run state."""

from collections import Counter
from datetime import datetime
from itertools import pairwise

from pydantic import ValidationError

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
    "request_review": "{metric_ids:string[],reason:string} -> flag a possible conflict for Team Lead",
    "assess_conflicts": "{conflicts:[{metric_ids:string[],reason:string,evidence_ids:string[]}],reason:string} -> Team Lead decides which semantic conflicts exist after inspecting all findings and source",
    "submit_review": "{decision:uphold|revise|unresolved,reason,evidence_ids:string[]} Team Lead arbitration only",
    "submit_evaluation": "{findings:FindingInput[],complete?:boolean} -> submit/revise owned metrics; complete=true finishes if all metrics and messages handled",
    "wait": "{} -> wait for another agent; finish when all metrics covered and inbox handled",
    "finish": "{} -> complete only if all assigned metrics submitted and all messages processed",
}


class TeamTools:
    def __init__(self, settings, knowledge):
        self.settings = settings
        self.knowledge = knowledge

    @staticmethod
    def ensure_team_lead(state):
        team = state["team"]
        if "team_lead" not in team["tasks"]:
            lead = task("team_lead", "arbitration", list(state["skills"]["metrics"]), "team_lead")
            lead["pending_conflicts"] = []
            lead["phase"] = "detect"
            lead["evaluation_run_id"] = state["run_id"]
            team["tasks"]["team_lead"] = lead
        return team["tasks"]["team_lead"]

    def add_review(self, state, conflict):
        team = state["team"]
        if conflict.get("reviewer"):
            return conflict["reviewer"]
        if team["reviews_created"] >= self.settings.max_reviews:
            conflict["status"] = "UNRESOLVED"
            conflict["reason"] = "review_budget_exhausted"
            return None
        agent = "team_lead"
        if agent not in team["tasks"]:
            team["tasks"][agent] = task(
                agent, "arbitration", conflict["metric_ids"], "team_lead",
                conflict["conflict_id"],
            )
            team["tasks"][agent]["pending_conflicts"] = []
            team["tasks"][agent]["evaluation_run_id"] = state["run_id"]
        else:
            lead = team["tasks"][agent]
            lead["metric_ids"] = list(dict.fromkeys(lead["metric_ids"] + conflict["metric_ids"]))
            if lead["status"] == "FAILED":
                conflict.update(status="UNRESOLVED", reason="team_lead_unavailable")
                return None
            if lead["conflict_id"] is None:
                lead["conflict_id"] = conflict["conflict_id"]
                lead["status"] = "PENDING"
            else:
                lead["pending_conflicts"].append(conflict["conflict_id"])
        team["reviews_created"] += 1
        conflict["reviewer"] = agent
        event(
            team,
            "team_lead",
            "assign_arbitration",
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
        if not isinstance(evidence_ids, list):
            raise TypeError("evidence_ids must be a list of registered strings")
        unknown = [e for e in evidence_ids if not isinstance(e, str) or e not in team["evidence"]]
        if unknown:
            # Exact IDs (not dialogue text) make retries actionable; validation stays strict.
            bad = [str(e)[:80] for e in unknown[:4]]
            available = list(team["evidence"])[:8]
            raise ValueError(f"Unknown evidence reference: {bad!r}. "
                             f"Registered IDs include {available!r}; copy dialogue.messages[].evidence_id exactly.")

    def request_review(self, state, sender, args):
        ids = args["metric_ids"]
        if not ids or any(mid not in state["skills"]["metrics"] for mid in ids):
            raise ValueError("Review needs known metric IDs")
        if not args.get("reason"):
            raise ValueError("Review reason required")
        report = {"metric_ids": ids, "reason": str(args["reason"])[:3000], "reported_by": sender}
        state["team"].setdefault("conflict_reports", []).append(report)
        return {"status": "queued_for_team_lead", "report": report}

    def assess_conflicts(self, state, agent, args):
        team = state["team"]
        lead = team["tasks"][agent]
        if lead["kind"] != "team_lead" or lead.get("phase") != "detect":
            raise ValueError("Only Team Lead may assess conflicts before arbitration")
        if not isinstance(args.get("reason"), str) or not args["reason"].strip():
            raise ValueError("Conflict assessment needs a reason, including when none exist")
        candidates = args.get("conflicts")
        if not isinstance(candidates, list):
            raise TypeError("Conflict assessment needs a conflicts list")
        findings = active_findings(team)
        prepared = []
        seen = set()
        for item in candidates:
            if not isinstance(item, dict):
                raise TypeError("Invalid conflict candidate")
            ids = item.get("metric_ids")
            if not isinstance(ids, list) or len(set(ids)) < 2 or any(mid not in findings for mid in ids):
                raise ValueError("Conflict must link at least two evaluated metrics")
            if not isinstance(item.get("reason"), str) or not item["reason"].strip():
                raise ValueError("Conflict needs a semantic reason")
            evidence_ids = item.get("evidence_ids", [])
            self.check_evidence(team, evidence_ids)
            if not evidence_ids:
                raise ValueError("Confirmed conflict needs original source evidence")
            signature = tuple(sorted(set(ids)))
            if signature in seen:
                raise ValueError("Duplicate conflict candidate")
            seen.add(signature)
            prepared.append((ids, item["reason"], evidence_ids))
        lead["phase"] = "arbitrate"
        for ids, reason, evidence_ids in prepared:
            cid = uid("conflict")
            conflict = {
                "conflict_id": cid, "signature": cid, "metric_ids": ids,
                "description": reason[:3000], "status": "OPEN", "review": None,
                "kind": "llm_semantic_conflict", "reported_by": agent,
                "evidence_ids": evidence_ids,
                "finding_ids": [findings[mid]["finding_id"] for mid in ids],
            }
            team["conflicts"][cid] = conflict
            self.add_review(state, conflict)
        if not lead["conflict_id"]:
            lead["status"] = "COMPLETED"
        event(team, agent, "assess_conflicts", {"count": len(prepared), "reason": args["reason"][:500]})
        return {"confirmed_conflicts": len(prepared), "status": lead["status"]}

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
            # 全文引用与预注册共享同一个确定性 ID（e-<message_id>），子串引用保持随机 ID。
            evidence_id = (
                "e-" + evidence.message_id
                if evidence.quote == message["content"]
                else uid("evidence")
            )
            item = {
                "evidence_id": evidence_id,
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
        if name == "assess_conflicts":
            return self.assess_conflicts(state, agent, args)
        if name == "submit_review":
            if (current["kind"] != "team_lead" or not current["skills_read"]
                    or current.get("phase") != "arbitrate" or not current["conflict_id"]):
                raise ValueError("Only Team Lead with loaded Skills may submit arbitration")
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
                        "content": f"Team Lead arbitration ({args['decision']}): {args['reason']}",
                        "evidence_ids": args.get("evidence_ids", []),
                        "related_indicators": conflict["metric_ids"],
                    },
                )
            current["conflict_id"] = (
                current["pending_conflicts"].pop(0) if current["pending_conflicts"] else None
            )
            current["status"] = "PENDING" if current["conflict_id"] else "COMPLETED"
            return {"status": "arbitration_submitted", "score_override": False}
        if name == "submit_evaluation":
            return self.submit(state, agent, args)
        if name == "wait":
            if current["kind"] == "evaluator" and (
                set(current["findings"]) != set(current["metric_ids"])
                or current.get("submission_errors")
            ) and not pending_messages(team, agent):
                raise ValueError("Submit missing/corrected metrics before waiting")
            current["status"] = "WAITING"
            return {"status": "WAITING"}
        if name == "finish":
            if current["kind"] == "team_lead":
                raise ValueError("Team Lead must submit_review")
            if current.get("submission_errors") or set(current["findings"]) != set(current["metric_ids"]) or pending_messages(
                team, agent
            ):
                raise ValueError("Required metrics or incoming messages remain unfinished")
            current["status"] = "COMPLETED"
            return {"status": "COMPLETED"}
        raise ValueError("Unknown tool")

    def submit(self, state, agent, args):
        """Validate independently: one rejected metric must not discard valid siblings."""
        current = state["team"]["tasks"][agent]
        if current["kind"] != "evaluator" or not current["skills_read"]:
            raise ValueError("Only assigned evaluators with loaded Skills may submit scores")
        items = args.get("findings")
        if not isinstance(items, list) or not items:
            raise ValueError("findings must be a non-empty list")
        counts = Counter(f.get("metric_id") for f in items
                         if isinstance(f, dict) and isinstance(f.get("metric_id"), str))
        accepted, rejected = [], []
        errors = current.setdefault("submission_errors", {})
        for index, item in enumerate(items):
            mid = item.get("metric_id") if isinstance(item, dict) else None
            if not isinstance(mid, str):
                mid = None
            try:
                if mid and counts[mid] > 1:
                    raise ValueError("Duplicate metric in this submission; submit it once")
                result = self._submit_validated(state, agent, {"findings": [item]})
                accepted.extend(result["accepted"])
                errors.pop(mid, None)
            except (ValueError, KeyError, TypeError) as error:
                detail = {"index": index, "metric_id": mid, "error": str(error)[:500]}
                if isinstance(error, ValidationError):
                    detail["error"] = "finding_schema_error"
                    detail["fields"] = [
                        {"path": list(e["loc"]), "type": e["type"]}
                        for e in error.errors()
                    ]
                rejected.append(detail)
                if mid in current["metric_ids"]:
                    errors[mid] = detail
        remaining = [mid for mid in current["metric_ids"] if mid not in current["findings"]]
        if (args.get("complete") is True and not remaining and not rejected
                and not errors and not pending_messages(state["team"], agent)):
            current["status"] = "COMPLETED"
        elif rejected:
            current["status"] = "RUNNING"
        return {"accepted": accepted, "rejected": rejected, "remaining_metric_ids": remaining,
                "status": current["status"],
                "next": "Correct only rejected or remaining metrics; do not resubmit accepted ones."}

    def _submit_validated(self, state, agent, args):
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
                    "SKILL.md status is published: rubric_unpublished does not apply"
                )
            if spec["status"] == "draft" and f.status == "NOT_EVALUABLE":
                context_rules = {"source_incomplete", "context_ambiguous", "source_conflict"}
                if not ({"rubric_unpublished"} | context_rules).intersection(f.review_rule_ids):
                    raise ValueError("Draft metric needs rubric_unpublished or context review")
            if f.status == "NOT_APPLICABLE" and "rubric_unpublished" in f.review_rule_ids:
                raise ValueError("Not-applicable metric cannot be rubric_unpublished")
            scoring_blockers = set(spec.get("scoring_blockers", []))
            if f.status == "EVALUATED" and scoring_blockers:
                raise ValueError(
                    "Metric scoring is blocked by configuration: "
                    + ", ".join(sorted(scoring_blockers))
                )
            if f.status == "NOT_EVALUABLE" and not scoring_blockers.issubset(
                f.review_rule_ids
            ):
                raise ValueError("Blocked metric needs matching manual review rules")
            if f.score is not None:
                if spec["status"] != "published" or spec["configuration_issues"]:
                    raise ValueError("Skill not published consistently; submit NOT_EVALUABLE")
                if f.score not in spec["score_values"] or not f.evidence_ids or not f.claims:
                    raise ValueError("Score needs a Skill anchor and source-grounded claims")
                if f.review_rule_ids:
                    raise ValueError("Unresolved review rules cannot carry a score")
                time_fact = spec.get("time_fact")
                facts = current.get("time_facts", {})
                if time_fact == "first_response_seconds" and not facts.get(
                    "first_response_available"
                ):
                    raise ValueError("Reliable first-response time missing")
                if time_fact == "adjacent_response_intervals" and not facts.get(
                    "adjacent_response_available"
                ):
                    raise ValueError("Reliable interaction response intervals missing")
                if not time_fact and "time_calculator" in spec.get("required_tools", []) and not facts.get(
                    "available"
                ):
                    raise ValueError("Required reliable time facts missing")
            prior = current["findings"].get(f.metric_id)
            if prior and all(prior.get(key) == value for key, value in f.model_dump().items()):
                # Repeating an accepted result is not a substantive revision.
                prepared.append(prior)
                continue
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
            if current["findings"].get(finding["metric_id"]) is finding:
                continue
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
        first_response_available = seconds is not None and seconds >= 0
        return {
            "available": first_response_available,
            "first_response_available": first_response_available,
            "adjacent_response_available": bool(pairs),
            "first_response_seconds": seconds if seconds is not None and seconds >= 0 else None,
            "adjacent_response_intervals": pairs,
            "limitation": "Adjacent intervals do not prove semantic question/answer pairing",
        }
