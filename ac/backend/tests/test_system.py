import json

import httpx
import pytest

from tests.conftest import login, wait_run

NS = "sim-northstar-mobility"
CRESTLINE = "sim-crestline-motors"


def claim(company, n):
    return f"{company}-CLAIM-2026-0{n}"


def test_each_company_has_different_sensor_counts(client, auditor):
    counts = {c["company_id"]: c["sensor_count"] for c in client.get("/api/v1/companies", headers=auditor).json()}
    assert sorted(counts.values()) == [3, 4, 5, 6, 8]


def test_sensor_data_is_complete_monthly_data(client, auditor):
    rollup = client.get("/api/v1/sensors/monthly-rollup", params={"company_id": NS}, headers=auditor).json()
    assert [r["month_number"] for r in rollup][:5] == [1, 2, 3, 4, 5]
    assert all(r["status"] == "SEALED" and r["summary_hash"] for r in rollup[:5])
    assert rollup[0]["sensor_count"] == 5 and rollup[0]["reading_count"] > 14000
    page = client.get(f"/api/v1/sensors/{rollup[0]['sensors'][0]['sensor_id']}/readings",
                      params={"company_id": NS, "month_number": 1, "limit": 5}, headers=auditor).json()
    assert page["total"] == 2880 and len(page["rows"]) == 5


def test_company_scoping_blocks_cross_company_access(client, operator):
    r = client.get("/api/v1/sensors", params={"company_id": CRESTLINE}, headers=operator)
    assert r.status_code == 403
    r = client.get("/api/v1/dashboard/claims", headers=operator)  # defaults to own company
    assert r.status_code == 200 and all(c["claim_id"].startswith(NS) for c in r.json())
    bad = client.post("/api/v1/verifications/run", params={"company_id": NS},
                      json={"claim_id": claim(CRESTLINE, 1), "mode": "DETERMINISTIC"}, headers=operator)
    assert bad.status_code == 404


def test_unauthenticated_ingest_rejected(client):
    r = client.post("/api/v1/sensor-readings", json={
        "sensor_id": "SCD40-NSM-PNT-01", "timestamp": "2026-06-01T00:00:00Z", "sequence_number": 99999,
        "co2_ppm": 500, "temperature_c": 25, "humidity_percent": 50})
    assert r.status_code == 401


def test_live_simulator_builds_and_seals_a_new_month(client, operator):
    start = client.post("/api/v1/simulation/start", json={"interval_seconds": 1}, headers=operator).json()
    assert start["running"] and start["current_month"] == 6
    client.post("/api/v1/simulation/stop", headers=operator)
    client.post("/api/v1/simulation/fault", json={"sensor_id": "SCD40-NSM-PRS-01", "kind": "STUCK", "hours": 12}, headers=operator)
    r = client.post("/api/v1/simulation/advance", json={"steps": 96}, headers=operator).json()
    assert r["readings_written"] == 96 * 5
    done = client.post("/api/v1/simulation/complete-month", headers=operator).json()
    assert 6 in done["sealed_months"]
    rollup = client.get("/api/v1/sensors/monthly-rollup", headers=operator).json()
    m6 = next(x for x in rollup if x["month_number"] == 6)
    assert m6["status"] == "SEALED" and m6["completeness_percent"] > 99
    stuck = next(s for s in m6["sensors"] if s["sensor_id"] == "SCD40-NSM-PRS-01")
    assert stuck["stuck_count"] >= 6


def test_deterministic_runs_vary_by_company(client, auditor):
    outcomes = {}
    for company, n in [(NS, 1), (NS, 4), (CRESTLINE, 4)]:
        r = client.post("/api/v1/verifications/run", params={"company_id": company},
                        json={"claim_id": claim(company, n), "mode": "DETERMINISTIC"}, headers=auditor)
        assert r.status_code == 202
        d = wait_run(client, auditor, company, r.json()["run_id"])
        assert d["status"] == "COMPLETED", d
        outcomes[(company, n)] = d["final_recommendation"]
    assert outcomes[(NS, 1)] == "RECOMMEND_APPROVAL"
    assert outcomes[(NS, 4)] == "RECOMMEND_REJECTION"
    assert outcomes[(CRESTLINE, 4)] == "ADDITIONAL_EVIDENCE_REQUIRED"  # main meter calibration expired


def test_agentic_flow_with_mocked_groq(client, auditor, monkeypatch):
    from app.agents import orchestrator
    from app.agents.groq_client import GroqClient
    from app.core.config import settings

    monkeypatch.setattr(settings, "groq_api_key", "test-key")
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        system = body["messages"][0]["content"]
        if "CONSENSUS_AGENT" in system:  # tries to be lenient; the guard must override it
            out = {"final_recommendation": "RECOMMEND_APPROVAL", "confidence": 0.9, "primary_reason": "Looks fine.",
                   "explanation": "x", "auditor_actions": ["Approve"], "dissenting_points": []}
        elif "DEBATE round" in system:
            out = {"responses": [{"to_agent": "TRUST_AND_FRAUD_AGENT", "message": "Agreed."}], "changed_position": False,
                   "revised_status": "PASS", "revised_risk_level": "LOW", "revised_confidence": 0.8, "final_statement": "Holding."}
        else:
            out = {"status": "HIGH_RISK", "risk_level": "HIGH", "confidence": 0.8, "summary": "Evidence reviewed.",
                   "findings": [{"title": "Gap", "detail": "d", "severity": "HIGH", "evidence_fields": ["claim.discrepancy_percent"]}],
                   "challenges": [{"to_agent": "COMPLIANCE_AGENT", "question": "Is this blocking?"}], "recommended_action": "Review"}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(out)}, "finish_reason": "stop"}],
                                         "usage": {"total_tokens": 100}})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(orchestrator, "make_client", lambda: GroqClient(transport=transport, sleep=lambda s: None))
    r = client.post("/api/v1/verifications/run", params={"company_id": NS},
                    json={"claim_id": claim(NS, 4), "mode": "AGENTIC"}, headers=auditor)
    assert r.status_code == 202
    d = wait_run(client, auditor, NS, r.json()["run_id"])
    assert d["status"] == "COMPLETED", d
    res = d["result"]
    assert res["execution_mode"] == "AGENTIC_GROQ" and d["llm_calls"] == 9  # 4 + 4 + 1
    assert res["consensus"]["llm_recommendation"] == "RECOMMEND_APPROVAL"
    assert res["consensus"]["final_recommendation"] == "RECOMMEND_REJECTION"  # guard prevented leniency
    assert res["consensus"]["guard_override"] is True
    assert {m["message_type"] for m in res["debate_messages"]} >= {"ASSESSMENT", "CHALLENGE", "RESPONSE", "CONSENSUS_NOTE"}
    assert all(b["model"] == "openai/gpt-oss-120b" for b in seen)


def test_groq_failure_falls_back_to_rules(client, auditor, monkeypatch):
    from app.agents import orchestrator
    from app.agents.groq_client import GroqClient
    from app.core.config import settings

    monkeypatch.setattr(settings, "groq_api_key", "bad")
    monkeypatch.setattr(orchestrator, "make_client", lambda: GroqClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(401, text="no")), sleep=lambda s: None))
    r = client.post("/api/v1/verifications/run", params={"company_id": NS},
                    json={"claim_id": claim(NS, 3), "mode": "AUTO"}, headers=auditor)
    d = wait_run(client, auditor, NS, r.json()["run_id"])
    assert d["status"] == "COMPLETED" and d["execution_mode"] == "DETERMINISTIC_FALLBACK"
    assert "API key" in d["result"]["llm"]["fallback_reason"]


def test_agentic_without_key_is_rejected(client, auditor):
    r = client.post("/api/v1/verifications/run", params={"company_id": NS},
                    json={"claim_id": claim(NS, 2), "mode": "AGENTIC"}, headers=auditor)
    assert r.status_code == 400


def test_decision_report_and_hash_chain_registry(client, auditor):
    cid, cl = NS, claim(NS, 4)
    assert client.post("/api/v1/audit/register/" + cl, params={"company_id": cid}, headers=auditor).status_code == 409
    d = client.post("/api/v1/auditor/decisions", params={"company_id": cid},
                    json={"claim_id": cl, "decision": "REJECT", "comments": "Main meter spoofed."}, headers=auditor)
    assert d.status_code == 201
    rec = client.post("/api/v1/audit/register/" + cl, params={"company_id": cid}, headers=auditor)
    assert rec.status_code == 201 and rec.json()["block_number"] == 1
    ver = client.get(f"/api/v1/audit/records/{cl}/verify", params={"company_id": cid}, headers=auditor).json()
    assert ver["status"] == "VERIFIED"
    # a later decision must not create a false tamper alarm
    client.post("/api/v1/auditor/decisions", params={"company_id": cid},
                json={"claim_id": cl, "decision": "ESCALATE", "comments": "Second opinion."}, headers=auditor)
    ver = client.get(f"/api/v1/audit/records/{cl}/verify", params={"company_id": cid}, headers=auditor).json()
    assert ver["status"] == "VERIFIED" and ver["newer_decision_exists"] is True
    assert client.post("/api/v1/audit/register/" + cl, params={"company_id": cid}, headers=auditor).status_code == 409
    assert client.get("/api/v1/audit/chain/verify", headers=auditor).json()["valid"] is True
    html = client.get(f"/api/v1/reports/{cl}", params={"company_id": cid}, headers=auditor)
    assert html.status_code == 200 and "AgentCarbon Verification Report" in html.text


def test_document_upload_rules(client, operator, auditor):
    cl = claim(NS, 3)
    good = client.post("/api/v1/documents/upload", headers=operator, data={"claim_id": cl, "document_type": "MAINTENANCE_RECORD"},
                       files={"file": ("rep.pdf", b"%PDF-1.4 test", "application/pdf")})
    assert good.status_code == 201
    fake = client.post("/api/v1/documents/upload", headers=operator, data={"claim_id": cl, "document_type": "OTHER"},
                       files={"file": ("evil.pdf", b"<html>x</html>", "application/pdf")})
    assert fake.status_code == 400
    exe = client.post("/api/v1/documents/upload", headers=operator, data={"claim_id": cl, "document_type": "OTHER"},
                      files={"file": ("a.exe", b"MZ", "application/octet-stream")})
    assert exe.status_code == 400
    other = client.post("/api/v1/documents/upload", headers=operator, data={"claim_id": claim(CRESTLINE, 3), "document_type": "OTHER"},
                        files={"file": ("rep.pdf", b"%PDF-1.4 x", "application/pdf")})
    assert other.status_code == 404
    ok = client.patch(f"/api/v1/documents/{good.json()['document_id']}/verify", params={"company_id": NS},
                      json={"status": "VERIFIED"}, headers=auditor)
    assert ok.json()["verification_status"] == "VERIFIED"


def test_login_throttle(client):
    for _ in range(8):
        client.post("/api/v1/auth/login", data={"username": "nobody@x.com", "password": "bad"})
    assert client.post("/api/v1/auth/login", data={"username": "nobody@x.com", "password": "bad"}).status_code == 429
