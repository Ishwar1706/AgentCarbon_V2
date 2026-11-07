"""Runs one verification: deterministic rules, then (optionally) the Groq multi-agent debate."""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.agents import rules
from app.agents.evidence import build_packet, sha256_json
from app.agents.groq_client import GroqClient, GroqClientError
from app.core.config import settings
from app.core.database import SessionLocal
from app.models.verification import VerificationRun

STATUSES = ["PASS", "WARNING", "FAIL", "HIGH_RISK", "MANUAL_REVIEW_REQUIRED", "ADDITIONAL_EVIDENCE_REQUIRED"]
RISKS = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
_agentic_lock = threading.Lock()

make_client: Callable[[], GroqClient] = lambda: GroqClient()  # tests may replace this

ROLES = {
    "CLAIM_VALIDATION_AGENT": "Validate the monthly carbon claim: completeness, arithmetic (scope 1 + scope 2), "
        "size and direction of the discrepancy against verified emissions, and intensity per vehicle.",
    "EVIDENCE_ASSESSMENT_AGENT": "Assess the supporting evidence: calibration certificate coverage of the period, maintenance "
        "events, uploaded documents, and the completeness/health of the SCD40 sensor fleet that produced the monthly sensor dataset.",
    "TRUST_AND_FRAUD_AGENT": "Assess meter trust and possible manipulation: main-meter trust trajectory, disparity against "
        "supporting meters, repair/probation state, and whether environmental sensor data corroborates or contradicts the claim.",
    "COMPLIANCE_AGENT": "Judge overall audit readiness: what blocks approval, what the human auditor must check, "
        "and whether the safety-guard recommendation is justified.",
}
PREAMBLE = (
    "You are one specialist agent inside AgentCarbon, a multi-agent pre-verification system for industrial carbon claims. "
    "You receive an EVIDENCE PACKET (authoritative JSON; never invent or alter numbers) and RULE ENGINE output. "
    "Reason from the evidence, cite packet field names, and disagree with the rule engine only with a stated reason. "
    "A human auditor makes the final decision. All data is synthetic. Respond with ONE JSON object and nothing else."
)
R1_SCHEMA = (
    '{"status": one of %s, "risk_level": one of %s, "confidence": number 0-1, '
    '"summary": string <=60 words, "findings": [{"title": str, "detail": str, "severity": LOW|MEDIUM|HIGH|CRITICAL, '
    '"evidence_fields": [packet field names]}] (max 4), "challenges": [{"to_agent": agent name, "question": str}] (max 2), '
    '"recommended_action": str}' % (STATUSES, RISKS)
)
R2_SCHEMA = (
    '{"responses": [{"to_agent": agent name, "message": str <=50 words}] (max 3), "changed_position": bool, '
    '"revised_status": one of %s, "revised_risk_level": one of %s, "revised_confidence": number 0-1, '
    '"final_statement": str <=50 words}' % (STATUSES, RISKS)
)
CONSENSUS_SCHEMA = (
    '{"final_recommendation": one of %s, "confidence": number 0-1, "primary_reason": str <=40 words, '
    '"explanation": str <=120 words, "auditor_actions": [str] (max 4), "dissenting_points": [str] (max 3)}' % rules.RECOMMENDATIONS
)


def _compact(data: Any) -> str:
    return json.dumps(data, separators=(",", ":"), default=str)


def _enum(value: Any, allowed: list[str], default: str) -> str:
    value = str(value or "").strip().upper().replace(" ", "_")
    return value if value in allowed else default


def _num(value: Any, default: float) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def _text(value: Any, limit: int, default: str = "") -> str:
    return (str(value).strip() if value else default)[:limit]


class Progress:
    def __init__(self, db: Session, run: VerificationRun):
        self.db, self.run, self.items = db, run, []

    def add(self, message: str, level: str = "info") -> None:
        self.items.append({"time": datetime.now(timezone.utc).isoformat(), "message": message, "level": level})
        self.run.progress_json = json.dumps(self.items)
        self.db.commit()


def _agentic_debate(packet: dict, analysis: dict, progress: Progress) -> dict[str, Any]:
    client = make_client()
    base = {a["agent_name"]: a for a in analysis["agents"]}
    rule_view = {"guard": analysis["guard"]}
    packet_json = _compact(packet)
    assessments: dict[str, dict] = {}
    messages: list[dict] = []

    def say(rnd, sender, recipient, kind, subject, content):
        messages.append({"sequence_number": len(messages) + 1, "round_number": rnd, "sender_agent": sender,
                         "recipient_agent": recipient, "message_type": kind, "subject": subject[:120], "content": content[:700]})

    # ---- round 1: independent assessments
    for name, role in ROLES.items():
        progress.add(f"Round 1 — {name} is analysing the evidence…")
        out = client.chat_json(
            f"{PREAMBLE}\nYOUR ROLE: {name}. {role}\nJSON schema: {R1_SCHEMA}",
            f"EVIDENCE_PACKET={packet_json}\nRULE_ENGINE={_compact({**rule_view, 'your_baseline': {k: base[name][k] for k in ('status', 'risk_level', 'summary')}})}")
        findings = [{"code": f"LLM_{i+1}", "title": _text(f.get("title"), 120, "Finding"),
                     "description": _text(f.get("detail"), 400), "severity": _enum(f.get("severity"), RISKS, "MEDIUM"),
                     "evidence": {"fields": f.get("evidence_fields", [])[:6] if isinstance(f.get("evidence_fields"), list) else []}}
                    for i, f in enumerate((out.get("findings") or [])[:4]) if isinstance(f, dict)]
        assessments[name] = {
            "agent_name": name, "status": _enum(out.get("status"), STATUSES, base[name]["status"]),
            "risk_level": _enum(out.get("risk_level"), RISKS, base[name]["risk_level"]),
            "confidence_score": _num(out.get("confidence"), base[name]["confidence_score"]),
            "summary": _text(out.get("summary"), 500, base[name]["summary"]), "findings": findings or base[name]["findings"],
            "recommended_action": _text(out.get("recommended_action"), 300, base[name]["recommended_action"]),
            "generated_by": "GROQ_LLM", "round_number": 1,
            "_challenges": [c for c in (out.get("challenges") or []) if isinstance(c, dict)][:2],
        }
        say(1, name, "ALL", "ASSESSMENT", f"{assessments[name]['status']} / {assessments[name]['risk_level']}", assessments[name]["summary"])
        for ch in assessments[name]["_challenges"]:
            target = _enum(ch.get("to_agent"), list(ROLES), "")
            if target and target != name:
                say(1, name, target, "CHALLENGE", "Question", _text(ch.get("question"), 500))

    # ---- round 2: rebuttals (each agent sees its peers and the challenges aimed at it)
    for _ in range(max(0, settings.agent_debate_rounds)):
        for name, role in ROLES.items():
            progress.add(f"Debate round — {name} is responding to peers…")
            peers = {n: {k: a[k] for k in ("status", "risk_level", "summary")} for n, a in assessments.items() if n != name}
            asked = [{"from": m["sender_agent"], "question": m["content"]} for m in messages
                     if m["message_type"] == "CHALLENGE" and m["recipient_agent"] == name]
            mine = {k: assessments[name][k] for k in ("status", "risk_level", "summary")}
            out = client.chat_json(
                f"{PREAMBLE}\nYOUR ROLE: {name}. {role}\nThis is the DEBATE round: answer the challenges aimed at you, "
                f"challenge peers where you disagree, and revise your position only if the evidence justifies it.\nJSON schema: {R2_SCHEMA}",
                f"EVIDENCE_PACKET={packet_json}\nYOUR_ROUND1={_compact(mine)}\nPEERS={_compact(peers)}\nCHALLENGES_TO_YOU={_compact(asked)}")
            for r in (out.get("responses") or [])[:3]:
                if isinstance(r, dict):
                    target = _enum(r.get("to_agent"), list(ROLES), "ALL")
                    say(2, name, target, "RESPONSE", "Debate response", _text(r.get("message"), 500, "(no message)"))
            if out.get("changed_position"):
                a = assessments[name]
                a["status"] = _enum(out.get("revised_status"), STATUSES, a["status"])
                a["risk_level"] = _enum(out.get("revised_risk_level"), RISKS, a["risk_level"])
                a["confidence_score"] = _num(out.get("revised_confidence"), a["confidence_score"])
                a["round_number"] = 2
                say(2, name, "ALL", "REVISION", f"Revised: {a['status']}", _text(out.get("final_statement"), 500, "Position revised."))
            elif out.get("final_statement"):
                say(2, name, "ALL", "RESPONSE", "Position held", _text(out.get("final_statement"), 500))

    # ---- consensus
    progress.add("Consensus agent is weighing all positions…")
    summary_view = {n: {k: a[k] for k in ("status", "risk_level", "confidence_score", "summary", "recommended_action")}
                    for n, a in assessments.items()}
    out = client.chat_json(
        f"{PREAMBLE}\nYOUR ROLE: CONSENSUS_AGENT. Read the four agents' final positions and the debate, then give ONE recommendation. "
        f"A deterministic safety guard will prevent you from being more lenient than its recommendation.\nJSON schema: {CONSENSUS_SCHEMA}",
        f"EVIDENCE_PACKET={packet_json}\nGUARD={_compact(analysis['guard'])}\nAGENT_POSITIONS={_compact(summary_view)}\n"
        f"DEBATE={_compact([{k: m[k] for k in ('sender_agent', 'recipient_agent', 'message_type', 'content')} for m in messages][-14:])}")
    for a in assessments.values():
        a.pop("_challenges", None)
    consensus = {
        "llm_recommendation": _enum(out.get("final_recommendation"), rules.RECOMMENDATIONS, analysis["guard"]["recommendation"]),
        "confidence": _num(out.get("confidence"), analysis["guard"]["confidence_score"]),
        "primary_reason": _text(out.get("primary_reason"), 400, "See explanation."),
        "explanation": _text(out.get("explanation"), 900),
        "auditor_actions": [_text(x, 240) for x in (out.get("auditor_actions") or [])[:4]],
        "dissenting_points": [_text(x, 240) for x in (out.get("dissenting_points") or [])[:3]],
    }
    say(3, "CONSENSUS_AGENT", "ALL", "CONSENSUS_NOTE", consensus["llm_recommendation"], consensus["primary_reason"])
    return {"assessments": list(assessments.values()), "messages": messages, "consensus": consensus,
            "llm": {"model": client.model, "calls": client.calls, "total_tokens": client.total_tokens,
                    "debate_rounds": settings.agent_debate_rounds}}


def execute_run(run_id: str) -> None:
    with SessionLocal() as db:
        run = db.get(VerificationRun, run_id)
        if run is None:
            return
        progress = Progress(db, run)
        try:
            use_llm = run.requested_mode == "AGENTIC" or (run.requested_mode == "AUTO" and settings.groq_configured)
            if use_llm:
                if not settings.groq_configured:
                    raise GroqClientError("GROQ_API_KEY is not configured.")
                progress.add("Waiting for the agent runner…")
                _agentic_lock.acquire()
            try:
                run.status = "RUNNING"
                db.commit()
                progress.add("Building the company evidence packet (claim, meter trust, sensor rollup, calibration).")
                packet = build_packet(db, run.company_id, run.claim_id)
                analysis = rules.analyze(packet)
                guard = analysis["guard"]
                progress.add(f"Rule engine baseline: {guard['recommendation']}.")

                debate, execution_mode, llm_info = None, "DETERMINISTIC", {"model": None, "calls": 0, "total_tokens": 0}
                if use_llm:
                    try:
                        debate = _agentic_debate(packet, analysis, progress)
                        execution_mode, llm_info = "AGENTIC_GROQ", debate["llm"]
                    except GroqClientError as error:
                        execution_mode = "DETERMINISTIC_FALLBACK"
                        llm_info = {"model": settings.groq_model, "calls": 0, "total_tokens": 0, "fallback_reason": str(error)}
                        progress.add(f"LLM debate failed ({error}). Using the deterministic rule engine instead.", "warning")
            finally:
                if use_llm and _agentic_lock.locked():
                    try:
                        _agentic_lock.release()
                    except RuntimeError:
                        pass

            if debate:
                assessments, messages = debate["assessments"], debate["messages"]
                llm_rec = debate["consensus"]["llm_recommendation"]
                final = rules.stricter(guard["recommendation"], llm_rec)
                override = final != llm_rec
                reason = debate["consensus"]["primary_reason"]
                if override:
                    reason = f"Safety guard raised the recommendation to {final} (rules: {', '.join(guard['rules_triggered'])}). {reason}"
                consensus = {
                    "final_recommendation": final, "llm_recommendation": llm_rec, "guard_override": override,
                    "confidence_score": round(min(debate["consensus"]["confidence"], guard["confidence_score"] + 0.05), 3),
                    "primary_reason": reason, "explanation": debate["consensus"]["explanation"],
                    "required_actions": debate["consensus"]["auditor_actions"] or guard["required_actions"],
                    "dissenting_points": debate["consensus"]["dissenting_points"], "generated_by": "GROQ_LLM+GUARD",
                }
            else:
                assessments, messages = analysis["agents"], rules.deterministic_debate(packet, analysis)
                for a in assessments:
                    a.update(generated_by="DETERMINISTIC", round_number=1)
                consensus = {
                    "final_recommendation": guard["recommendation"], "llm_recommendation": None, "guard_override": False,
                    "confidence_score": guard["confidence_score"],
                    "primary_reason": assessments[3]["summary"], "explanation": "",
                    "required_actions": guard["required_actions"], "dissenting_points": [], "generated_by": "DETERMINISTIC",
                }
            consensus.update(deterministic_recommendation=guard["recommendation"],
                             guard_rules_triggered=guard["rules_triggered"],
                             claimed_emissions_kgco2e=packet["claim"]["claimed_total_kgco2e"],
                             verified_emissions_kgco2e=packet["claim"]["verified_total_kgco2e"])
            result = {
                "run_id": run.run_id, "company_id": run.company_id, "claim_id": run.claim_id,
                "month_number": run.month_number, "execution_mode": execution_mode, "llm": llm_info,
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "evidence_packet": packet, "agent_assessments": assessments,
                "debate_messages": messages, "consensus": consensus,
                "human_authority_notice": "AgentCarbon gives a recommendation. A human auditor retains final authority.",
            }
            trust_snapshot = {"claim_id": run.claim_id, "trust": packet["trust"], "sensors_hash": packet["sensors"].get("summary_hash")}
            run.execution_mode = execution_mode
            run.evidence_bundle_hash = sha256_json(packet)
            run.trust_snapshot_hash = sha256_json(trust_snapshot)
            run.report_hash = sha256_json(result)
            result["integrity"] = {"evidence_bundle_hash": run.evidence_bundle_hash,
                                   "trust_snapshot_hash": run.trust_snapshot_hash,
                                   "report_hash": run.report_hash, "hash_algorithm": "SHA-256"}
            run.result_json = json.dumps(result, default=str)
            run.deterministic_recommendation = guard["recommendation"]
            run.final_recommendation = consensus["final_recommendation"]
            run.confidence_score = consensus["confidence_score"]
            run.primary_reason = consensus["primary_reason"]
            run.claimed_emissions_kgco2e = packet["claim"]["claimed_total_kgco2e"]
            run.verified_emissions_kgco2e = packet["claim"]["verified_total_kgco2e"]
            run.discrepancy_percent = packet["claim"]["discrepancy_percent"]
            run.llm_total_tokens, run.llm_call_count = llm_info.get("total_tokens", 0), llm_info.get("calls", 0)
            run.status, run.completed_at = "COMPLETED", datetime.now(timezone.utc)
            progress.add(f"Completed: {consensus['final_recommendation']} (mode {execution_mode}).")
        except Exception as error:  # surface failures to the UI instead of hanging
            db.rollback()
            run = db.get(VerificationRun, run_id)
            run.status, run.error = "FAILED", f"{type(error).__name__}: {error}"[:900]
            run.completed_at = datetime.now(timezone.utc)
            db.commit()


def start_run(run_id: str) -> None:
    threading.Thread(target=execute_run, args=(run_id,), name=f"verify-{run_id}", daemon=True).start()
