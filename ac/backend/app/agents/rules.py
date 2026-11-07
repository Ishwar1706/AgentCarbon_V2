"""Deterministic rule engine: baseline assessments + the safety guard.

The guard is the floor under every recommendation: an LLM may be *stricter*
than the guard, never more lenient.
"""
from __future__ import annotations

from typing import Any

APPROVE, PROBATION, MANUAL, MORE_EVIDENCE, REJECT = (
    "RECOMMEND_APPROVAL", "APPROVAL_AFTER_PROBATION_REVIEW", "MANUAL_REVIEW",
    "ADDITIONAL_EVIDENCE_REQUIRED", "RECOMMEND_REJECTION",
)
SEVERITY = {APPROVE: 0, PROBATION: 1, MANUAL: 2, MORE_EVIDENCE: 3, REJECT: 4}
RECOMMENDATIONS = list(SEVERITY)
AGENTS = ("CLAIM_VALIDATION_AGENT", "EVIDENCE_ASSESSMENT_AGENT", "TRUST_AND_FRAUD_AGENT", "COMPLIANCE_AGENT")


def stricter(a: str, b: str) -> str:
    return a if SEVERITY.get(a, 0) >= SEVERITY.get(b, 0) else b


def _finding(code, title, description, severity, **evidence):
    return {"code": code, "title": title, "description": description,
            "severity": severity, "evidence": evidence}


def analyze(packet: dict[str, Any]) -> dict[str, Any]:
    c, t, s, d = packet["claim"], packet["trust"], packet["sensors"], packet["documents"]
    pct = c["discrepancy_percent"]
    material, severe = pct > 5.0, pct > 15.0
    trust_state = t.get("final_trust_state", "UNKNOWN")
    min_trust = t.get("minimum_main_meter_trust", 1.0)
    final_trust = t.get("final_main_meter_trust", 1.0)
    penalized_share = t.get("trust_state_record_counts", {}).get("PENALIZED", 0) / max(t.get("result_count", 1), 1)
    penalized = penalized_share >= 0.05 or final_trust < 0.6
    fault_pct = t.get("fault_detected_percent", 0.0)
    cal_ok = d["main_meter_calibration_valid_for_period"]
    sensor_ok = s.get("available") and s.get("completeness_percent", 0) >= 90
    flagged = s.get("flagged_sensor_count", 0)
    n_sensors = s.get("sensor_count", 0)

    # ---------- Agent 1: claim validation
    f1 = []
    if severe:
        f1.append(_finding("SEVERE_DISCREPANCY", "Severe claim discrepancy",
                           f"Claim is {pct:.2f}% {c['direction'].lower().replace('_', ' ')} versus verified emissions.",
                           "CRITICAL", discrepancy_percent=pct))
    elif material:
        f1.append(_finding("MATERIAL_DISCREPANCY", "Material claim discrepancy",
                           f"Claim differs by {pct:.2f}% from verified emissions.", "HIGH", discrepancy_percent=pct))
    else:
        f1.append(_finding("CLAIM_CONSISTENT", "Claim consistent",
                           f"Claim is within {pct:.2f}% of verified emissions.", "LOW", discrepancy_percent=pct))
    a1 = ("FAIL", "CRITICAL") if severe else ("WARNING", "HIGH") if material else ("PASS", "LOW")

    # ---------- Agent 2: evidence
    f2 = []
    if not cal_ok:
        f2.append(_finding("CALIBRATION_NOT_COVERING_PERIOD", "Main meter calibration does not cover the period",
                           "No valid calibration certificate covers the whole claim period for MTR-MAIN-001.",
                           "HIGH"))
    if not s.get("available"):
        f2.append(_finding("NO_SENSOR_DATA", "No sensor data", "No monthly sensor dataset exists for this period.", "HIGH"))
    elif not sensor_ok:
        f2.append(_finding("SENSOR_INCOMPLETE", "Sensor data incomplete",
                           f"Sensor completeness is {s['completeness_percent']}% (needs ≥ 90%).", "MEDIUM"))
    if flagged:
        f2.append(_finding("SENSOR_FAULTS", "Faulty or degraded sensors",
                           f"{flagged} of {n_sensors} sensors are flagged (stuck values, drift, dropouts or spikes).",
                           "MEDIUM", flagged=flagged))
    if not f2:
        f2.append(_finding("EVIDENCE_OK", "Evidence supports the claim period",
                           f"Calibration valid; {n_sensors} sensors with {s.get('completeness_percent')}% completeness.", "LOW"))
    a2 = ("ADDITIONAL_EVIDENCE_REQUIRED", "HIGH") if (not cal_ok or not sensor_ok) else \
         ("WARNING", "MEDIUM") if flagged else ("PASS", "LOW")

    # ---------- Agent 3: trust and fraud
    f3 = []
    if penalized or fault_pct > 10:
        f3.append(_finding("METER_SPOOFING_PATTERN", "Main meter deviates from supporting meters",
                           f"Main meter trust fell to {min_trust:.2f}; faults flagged in {fault_pct:.1f}% of records.",
                           "CRITICAL" if min_trust < 0.3 else "HIGH", minimum_trust=min_trust))
    if trust_state in ("PROBATION", "REHABILITATED") or d["repair_event_in_period"]:
        f3.append(_finding("REPAIR_AND_PROBATION", "Meter repaired and under probation",
                           f"Final trust state is {trust_state}.", "MEDIUM"))
    if s.get("co2_vs_month1_baseline_percent", 0) > 20 and c["direction"] == "UNDER_REPORTED":
        f3.append(_finding("SENSORS_CONTRADICT_CLAIM", "Environmental sensors contradict a low claim",
                           f"Average CO2 is {s['co2_vs_month1_baseline_percent']:+.1f}% versus the month-1 baseline "
                           "while the claim reports lower emissions.", "HIGH"))
    if not f3:
        f3.append(_finding("TRUST_STABLE", "Meters consistent", f"Trust state {trust_state}; no sustained faults.", "LOW"))
    a3 = ("HIGH_RISK", "CRITICAL" if min_trust < 0.3 else "HIGH") if (penalized or fault_pct > 10) else \
         ("WARNING", "MEDIUM") if len(f3) > 1 or f3[0]["severity"] != "LOW" else ("PASS", "LOW")

    # ---------- Guard / compliance
    rules: list[str] = []
    actions: list[str] = []
    if severe and (penalized or not cal_ok or not sensor_ok):
        rec = REJECT
        rules.append("SEVERE_DISCREPANCY_WITH_UNRELIABLE_EVIDENCE")
        actions.append("Reject the claim as filed and request a corrected, evidence-backed resubmission.")
    elif severe:
        rec = MANUAL
        rules.append("SEVERE_DISCREPANCY")
        actions.append("Auditor must review the discrepancy before any decision.")
    elif not cal_ok:
        rec = MORE_EVIDENCE
        rules.append("CALIBRATION_MISSING_FOR_PERIOD")
        actions.append("Obtain a calibration certificate covering the whole period for the main meter.")
    elif not sensor_ok:
        rec = MORE_EVIDENCE
        rules.append("SENSOR_DATA_INCOMPLETE")
        actions.append("Provide complete sensor data or an explanation for the gaps.")
    elif material or penalized:
        rec = MANUAL
        rules.append("MATERIAL_DISCREPANCY_OR_PENALIZED_METER")
        actions.append("Auditor manual review of meter trust history and claim variance.")
    elif trust_state in ("PROBATION", "REHABILITATED") or d["repair_event_in_period"]:
        rec = PROBATION
        rules.append("REPAIRED_METER_ON_PROBATION")
        actions.append("Review the repair work order and keep the meter under probation monitoring.")
    elif flagged:
        rec = PROBATION
        rules.append("SENSOR_FAULTS_NON_BLOCKING")
        actions.append("Schedule maintenance for the flagged sensors; claim itself is consistent.")
    else:
        rec = APPROVE
        rules.append("ALL_CHECKS_PASSED")
        actions.append("Auditor to confirm and approve.")
    if not rules:
        rules.append("NO_RULE")

    confidence = 0.95
    confidence -= 0.1 * (not sensor_ok) + 0.1 * (not cal_ok) + 0.05 * bool(flagged) + 0.05 * penalized
    confidence = round(max(0.5, min(0.97, confidence)), 3)
    status3 = {"PASS": "PASS"}.get(a3[0], a3[0])
    return {
        "agents": [
            {"agent_name": AGENTS[0], "status": a1[0], "risk_level": a1[1], "confidence_score": 0.95,
             "summary": f1[0]["description"], "findings": f1, "recommended_action": actions[0] if severe or material else "No action."},
            {"agent_name": AGENTS[1], "status": a2[0], "risk_level": a2[1], "confidence_score": 0.9,
             "summary": "; ".join(f["description"] for f in f2)[:400], "findings": f2,
             "recommended_action": "Collect missing evidence." if a2[0] != "PASS" else "No action."},
            {"agent_name": AGENTS[2], "status": status3, "risk_level": a3[1], "confidence_score": 0.9,
             "summary": "; ".join(f["description"] for f in f3)[:400], "findings": f3,
             "recommended_action": "Escalate meter inspection." if a3[0] != "PASS" else "No action."},
            {"agent_name": AGENTS[3], "status": "PASS" if rec == APPROVE else
             "MANUAL_REVIEW_REQUIRED" if rec in (MANUAL, PROBATION) else
             "ADDITIONAL_EVIDENCE_REQUIRED" if rec == MORE_EVIDENCE else "FAIL",
             "risk_level": "LOW" if rec == APPROVE else "MEDIUM" if rec == PROBATION else "HIGH" if rec in (MANUAL, MORE_EVIDENCE) else "CRITICAL",
             "confidence_score": confidence,
             "summary": f"Rule guard recommends {rec.replace('_', ' ').title()} ({', '.join(rules)}).",
             "findings": [_finding(r, r.replace("_", " ").title(), "Guard rule triggered.", "MEDIUM") for r in rules],
             "recommended_action": actions[0]},
        ],
        "guard": {"recommendation": rec, "rules_triggered": rules, "required_actions": actions, "confidence_score": confidence},
    }


def deterministic_debate(packet: dict[str, Any], analysis: dict[str, Any]) -> list[dict[str, Any]]:
    """Readable transcript for the no-LLM mode, derived from the rule findings."""
    a = {x["agent_name"]: x for x in analysis["agents"]}
    msgs = []
    def add(rnd, sender, recipient, kind, subject, content):
        msgs.append({"sequence_number": len(msgs) + 1, "round_number": rnd, "sender_agent": sender,
                     "recipient_agent": recipient, "message_type": kind, "subject": subject, "content": content})
    c = a[AGENTS[0]]; e = a[AGENTS[1]]; t = a[AGENTS[2]]; g = a[AGENTS[3]]
    add(1, AGENTS[0], AGENTS[2], "CHALLENGE", "Claim vs trust", f"{c['summary']} Does meter trust explain this?")
    add(1, AGENTS[2], AGENTS[0], "RESPONSE", "Trust analysis", t["summary"])
    add(1, AGENTS[1], AGENTS[3], "RESPONSE", "Evidence status", e["summary"])
    add(2, AGENTS[3], AGENTS[3], "CONSENSUS_NOTE", "Guard outcome", g["summary"])
    return msgs
