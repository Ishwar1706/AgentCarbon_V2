import json

import httpx

from tests.conftest import login, run_verification, submit_month, upload, wait_run

NS, CRESTLINE = "sim-northstar-mobility", "sim-crestline-motors"
DOCS = ("ELECTRICITY_BILL", "PRODUCTION_RECORD", "FUEL_BILL")


def test_unknown_api_path_returns_json_404(client):
    for path in ("/api/v1/not-a-real-endpoint", "/health-check"):
        response = client.get(path)
        assert response.status_code == 404
        assert response.headers["content-type"].startswith("application/json")
        assert response.json() == {"detail": "Not found"}


# ------------------------------------------------------------------ data
def test_each_company_has_different_sensor_counts(client, auditor):
    counts = {c["company_id"]: c["sensor_count"] for c in client.get("/api/v1/companies", headers=auditor).json()}
    assert sorted(counts.values()) == [3, 4, 5, 6, 8]


def test_calendar_months_and_no_data_months(client, auditor, operator):
    cal = client.get("/api/v1/calendar", params={"company_id": NS, "year": 2026}, headers=auditor).json()["months"]
    assert [m["label"] for m in cal][:5] == ["Jan 2026", "Feb 2026", "Mar 2026", "Apr 2026", "May 2026"]
    assert all(m["claim_data"] and m["sensor_data"] for m in cal[:5]) and not cal[7]["claim_data"]
    old = client.get("/api/v1/calendar", params={"company_id": NS, "year": 2025}, headers=auditor).json()["months"]
    assert not any(m["claim_data"] or m["sensor_data"] for m in old)
    assert client.get("/api/v1/requests/2025-03", headers=operator).json()["available"] is False
    assert client.get("/api/v1/dashboard/overview", params={"company_id": NS, "period": "2025-03"},
                      headers=auditor).json()["available"] is False


def test_monthly_sensor_datasets_use_real_days_in_month(client, auditor):
    roll = {r["period"]: r for r in client.get("/api/v1/sensors/monthly-rollup", params={"company_id": NS}, headers=auditor).json()}
    assert [roll[p]["sensor_count"] for p in ("2026-01", "2026-02", "2026-03")] == [5, 5, 5]
    assert roll["2026-02"]["status"] == "SEALED" and roll["2026-02"]["summary_hash"]
    sid = roll["2026-02"]["sensors"][0]["sensor_id"]
    feb = client.get(f"/api/v1/sensors/{sid}/readings", params={"company_id": NS, "period": "2026-02", "limit": 1}, headers=auditor).json()
    jan = client.get(f"/api/v1/sensors/{sid}/readings", params={"company_id": NS, "period": "2026-01", "limit": 1}, headers=auditor).json()
    assert feb["total"] == 28 * 96 and jan["total"] == 31 * 96
    assert client.get("/api/v1/dashboard/claims", params={"company_id": NS}, headers=auditor).json()[1]["label"] == "Feb 2026"


def test_live_simulator_continues_from_june_and_seals(client, operator):
    start = client.post("/api/v1/simulation/start", json={"interval_seconds": 1}, headers=operator).json()
    assert start["running"] and start["current_period"] == "2026-06"
    client.post("/api/v1/simulation/stop", headers=operator)
    client.post("/api/v1/simulation/fault", json={"sensor_id": "SCD40-NSM-PRS-01", "kind": "STUCK", "hours": 12}, headers=operator)
    assert client.post("/api/v1/simulation/advance", json={"steps": 96}, headers=operator).json()["readings_written"] == 96 * 5
    done = client.post("/api/v1/simulation/complete-month", headers=operator).json()
    assert "2026-06" in done["sealed_periods"]
    roll = client.get("/api/v1/sensors/monthly-rollup", headers=operator).json()
    june = next(x for x in roll if x["period"] == "2026-06")
    assert june["status"] == "SEALED" and june["completeness_percent"] > 99
    assert next(s for s in june["sensors"] if s["sensor_id"] == "SCD40-NSM-PRS-01")["stuck_count"] >= 6


# ------------------------------------------------------------- role limits
def test_role_isolation(client, operator, admin, buyer, auditor):
    assert client.get("/api/v1/sensors", params={"company_id": "sim-crestline-motors"}, headers=operator).status_code == 403
    for h in (admin, buyer):
        for path in ("/api/v1/sensors", "/api/v1/dashboard/claims", "/api/v1/requests/2026-02", "/api/v1/info-requests"):
            assert client.get(path, params={"company_id": NS}, headers=h).status_code == 403, path
    assert client.get("/api/v1/admin/summary", headers=auditor).status_code == 403
    assert client.get("/api/v1/credits", headers=operator).status_code == 403
    assert client.post("/api/v1/simulation/start", json={}, params={"company_id": NS}, headers=auditor).status_code == 403


def test_unauthenticated_ingest_rejected(client):
    r = client.post("/api/v1/sensor-readings", json={
        "sensor_id": "SCD40-NSM-PNT-01", "timestamp": "2027-06-01T00:00:00Z", "sequence_number": 99999,
        "co2_ppm": 500, "temperature_c": 25, "humidity_percent": 50})
    assert r.status_code == 401


# ------------------------------------------------- operator request flow
def test_auditor_can_run_unsubmitted_month_but_cannot_finalize(client, auditor, operator):
    for period in ("2026-02", "2026-03"):
        if period == "2026-03":
            detail = client.get(f"/api/v1/requests/{period}", headers=operator).json()
            pre = detail["prefill"]
            saved = client.put(f"/api/v1/requests/{period}", headers=operator, json={
                "expected_credits_tco2e": pre["expected_credits_tco2e"],
                "declared_electricity_kwh": pre["electricity_kwh"],
                "declared_production_units": pre["production_units"],
                "declared_natural_gas_scm": pre["natural_gas_scm"],
                "declared_diesel_litres": pre["diesel_litres"],
            })
            assert saved.status_code == 200 and saved.json()["status"] == "DRAFT"

        run = run_verification(client, auditor, NS, period)
        assert run["result"]["evidence_packet"]["declared"]["source"] == "DATASET_PREFILL"
        assert run["result"]["evidence_packet"]["claim"]["request_status"] in {"NOT_SUBMITTED", "DRAFT"}
        assert client.post("/api/v1/auditor/decisions", params={"company_id": NS}, headers=auditor,
                           json={"period": period, "decision": "APPROVE", "comments": "Cannot approve yet."}).status_code == 409
        info = client.post("/api/v1/info-requests", params={"company_id": NS}, headers=auditor, json={
            "period": period, "title": "Please submit this month", "items": [
                {"kind": "INFORMATION", "label": "Please submit the monthly request."},
            ],
        })
        assert info.status_code == 409 and "not submitted" in info.json()["detail"]
        register = client.post(f"/api/v1/audit/register/{period}", params={"company_id": NS}, headers=auditor)
        assert register.status_code == 409 and "not submitted" in register.json()["detail"]

    missing = client.post("/api/v1/verifications/run", params={"company_id": NS}, headers=auditor,
                          json={"period": "2025-03", "mode": "DETERMINISTIC"})
    assert missing.status_code == 404 and "No data available for Mar 2025" in missing.json()["detail"]


def test_fresh_demo_seed_registers_two_buyer_credits(client, buyer):
    lots = client.get("/api/v1/credits", headers=buyer)
    assert lots.status_code == 200
    assert {(lot["company_id"], lot["label"]) for lot in lots.json()} == {
        ("sim-northstar-mobility", "Jan 2026"),
        ("sim-ironwood-automotive", "Jan 2026"),
    }


def test_agents_run_for_every_dataset_month_across_companies(client, auditor):
    for company in (NS, "sim-ironwood-automotive"):
        for month in range(1, 6):
            period = f"2026-{month:02d}"
            result = run_verification(client, auditor, company, period)
            assert result["period"] == period
            assert result["status"] == "COMPLETED"


def test_missing_evidence_triggers_info_request_loop_to_buyer_credit(client, operator, auditor, buyer):
    period = "2026-02"
    detail = client.get(f"/api/v1/requests/{period}", headers=operator).json()
    assert detail["request"] is None and detail["editable"] and len(detail["checklist"]["missing_required"]) == 3
    bad = client.put(f"/api/v1/requests/{period}", headers=operator, json={
        "expected_credits_tco2e": -1, "declared_electricity_kwh": 10, "declared_production_units": 1,
        "declared_natural_gas_scm": 0, "declared_diesel_litres": 0})
    assert bad.status_code == 422
    submit_month(client, operator, period)
    assert client.put(f"/api/v1/requests/{period}", headers=operator, json={
        "expected_credits_tco2e": 1, "declared_electricity_kwh": 10, "declared_production_units": 1,
        "declared_natural_gas_scm": 0, "declared_diesel_litres": 0}).status_code == 409  # locked after submit

    run = run_verification(client, auditor, NS, period)
    assert run["final_recommendation"] == "ADDITIONAL_EVIDENCE_REQUIRED"
    items = run["result"]["consensus"]["suggested_info_items"]
    assert {i["doc_type"] for i in items if i["kind"] == "DOCUMENT"} == set(DOCS)

    ir = client.post("/api/v1/info-requests", params={"company_id": NS}, headers=auditor, json={
        "period": period, "title": "Missing bills for Feb 2026", "message": "Please upload the bills.", "items": items})
    assert ir.status_code == 201, ir.text
    ir_id = ir.json()["request_id"]
    assert client.get(f"/api/v1/requests/{period}", headers=operator).json()["request"]["status"] == "INFO_REQUESTED"
    assert client.get("/api/v1/info-requests/summary", headers=operator).json() == {"open": 1, "unseen": 1, "responded": 0}
    assert client.post(f"/api/v1/info-requests/{ir_id}/reply", json={"answers": {}}, headers=operator).status_code == 400

    for slot in DOCS:
        assert upload(client, operator, period, slot, f"%PDF-1.4 {slot} feb".encode(), ir_id).status_code == 201
    ok = client.post(f"/api/v1/info-requests/{ir_id}/reply", json={"answers": {}, "note": "Attached."}, headers=operator)
    assert ok.status_code == 200 and ok.json()["status"] == "RESPONDED"
    assert client.get(f"/api/v1/requests/{period}", headers=operator).json()["request"]["status"] == "SUBMITTED"

    docs = client.get("/api/v1/documents", params={"company_id": NS, "period": period}, headers=auditor).json()
    for d in docs:
        assert client.patch(f"/api/v1/documents/{d['document_id']}/verify", params={"company_id": NS},
                            json={"status": "VERIFIED"}, headers=auditor).status_code == 200
    run2 = run_verification(client, auditor, NS, period)
    assert run2["final_recommendation"] == "RECOMMEND_APPROVAL"

    dec = client.post("/api/v1/auditor/decisions", params={"company_id": NS}, headers=auditor,
                      json={"period": period, "decision": "APPROVE", "comments": "All evidence received."})
    assert dec.status_code == 201
    assert client.get(f"/api/v1/requests/{period}", headers=operator).json()["request"]["status"] == "APPROVED"
    reg = client.post(f"/api/v1/audit/register/{period}", params={"company_id": NS}, headers=auditor)
    assert reg.status_code == 201
    lots = client.get("/api/v1/credits", headers=buyer).json()
    assert len(lots) == 3 and any(l["label"] == "Feb 2026" and l["approved_credits_tco2e"] > 0 for l in lots)
    claim_id = f"{NS}-CLAIM-2026-02"
    assert client.get(f"/api/v1/credits/{claim_id}/verify", headers=buyer).json()["status"] == "VERIFIED"
    assert "AgentCarbon Verification Report" in client.get(f"/api/v1/credits/{claim_id}/report", headers=buyer).text
    assert client.get("/api/v1/audit/chain/verify", headers=buyer).json()["valid"] is True


def test_overstated_credits_after_meter_manipulation_are_rejected(client, operator, auditor, buyer):
    submit_month(client, operator, "2026-04")  # Apr 2026: main meter spoofed, plant under-reports emissions
    run = run_verification(client, auditor, NS, "2026-04")
    packet = run["result"]["evidence_packet"]
    assert packet["credits"]["overstatement_percent"] > 50
    assert run["final_recommendation"] == "RECOMMEND_REJECTION"
    dec = client.post("/api/v1/auditor/decisions", params={"company_id": NS}, headers=auditor,
                      json={"period": "2026-04", "decision": "REJECT", "comments": "Credits overstated."})
    assert dec.status_code == 201
    assert client.post("/api/v1/audit/register/2026-04", params={"company_id": NS}, headers=auditor).status_code == 201
    assert all(l["label"] != "Apr 2026" for l in client.get("/api/v1/credits", headers=buyer).json())  # buyers never see rejected


def test_expired_calibration_is_fixed_by_a_verified_upload(client, auditor):
    op = login(client, "crestline@agentcarbon.demo")
    period = "2026-05"
    submit_month(client, op, period)
    run = run_verification(client, auditor, CRESTLINE, period)
    assert run["final_recommendation"] == "ADDITIONAL_EVIDENCE_REQUIRED"
    types = {i["doc_type"] for i in run["result"]["consensus"]["suggested_info_items"] if i["kind"] == "DOCUMENT"}
    assert "CALIBRATION_CERTIFICATE" in types and run["result"]["evidence_packet"]["documents"]["calibration_source"] == "NONE"
    for slot in (*DOCS, "CALIBRATION_CERTIFICATE"):
        r = upload(client, op, period, slot, f"%PDF-1.4 {slot} crestline".encode())
        assert r.status_code == 201
        assert client.patch(f"/api/v1/documents/{r.json()['document_id']}/verify", params={"company_id": CRESTLINE},
                            json={"status": "VERIFIED"}, headers=auditor).status_code == 200
    run2 = run_verification(client, auditor, CRESTLINE, period)
    assert run2["result"]["evidence_packet"]["documents"]["calibration_source"] == "VERIFIED_UPLOAD"
    assert run2["final_recommendation"] != "ADDITIONAL_EVIDENCE_REQUIRED"


def test_upload_rules(client, operator):
    cl = "2026-03"
    assert upload(client, operator, cl, "FUEL_BILL", b"%PDF-1.4 ok march").status_code == 201
    assert upload(client, operator, cl, "FUEL_BILL", b"<html>x</html>").status_code == 400
    assert upload(client, operator, cl, "NOT_A_TYPE", b"%PDF-1.4 x").status_code == 400
    assert upload(client, operator, "2025-03", "FUEL_BILL", b"%PDF-1.4 y").status_code == 404


# ---------------------------------------------------------- AI agents (mock)
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
        if "CONSENSUS_AGENT" in system:
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
    d = run_verification(client, auditor, NS, "2026-04", mode="AGENTIC")
    res = d["result"]
    assert res["execution_mode"] == "AGENTIC_GROQ" and d["llm_calls"] == 9
    assert res["consensus"]["llm_recommendation"] == "RECOMMEND_APPROVAL"
    assert res["consensus"]["final_recommendation"] == "RECOMMEND_REJECTION" and res["consensus"]["guard_override"] is True
    assert {m["message_type"] for m in res["debate_messages"]} >= {"ASSESSMENT", "CHALLENGE", "RESPONSE", "CONSENSUS_NOTE"}
    assert all(b["model"] == "openai/gpt-oss-120b" for b in seen)


def test_groq_failure_falls_back_to_rules(client, auditor, monkeypatch):
    from app.agents import orchestrator
    from app.agents.groq_client import GroqClient
    from app.core.config import settings

    monkeypatch.setattr(settings, "groq_api_key", "bad")
    monkeypatch.setattr(orchestrator, "make_client", lambda: GroqClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(401, text="no")), sleep=lambda s: None))
    d = run_verification(client, auditor, NS, "2026-04", mode="AUTO")
    assert d["execution_mode"] == "DETERMINISTIC_FALLBACK" and "API key" in d["result"]["llm"]["fallback_reason"]


def test_agentic_without_key_is_rejected(client, auditor):
    r = client.post("/api/v1/verifications/run", params={"company_id": NS},
                    json={"period": "2026-04", "mode": "AGENTIC"}, headers=auditor)
    assert r.status_code == 400


def test_registry_survives_newer_decisions(client, auditor):
    ver = client.get("/api/v1/audit/records/2026-04/verify", params={"company_id": NS}, headers=auditor).json()
    assert ver["status"] == "VERIFIED"
    assert client.post("/api/v1/auditor/decisions", params={"company_id": NS}, headers=auditor,
                       json={"period": "2026-04", "decision": "ESCALATE", "comments": "Second opinion."}).status_code == 201
    ver = client.get("/api/v1/audit/records/2026-04/verify", params={"company_id": NS}, headers=auditor).json()
    assert ver["status"] == "VERIFIED" and ver["newer_decision_exists"] is True
    assert client.post("/api/v1/audit/register/2026-04", params={"company_id": NS}, headers=auditor).status_code == 409


# ------------------------------------------------------------------ admin
def test_admin_account_lifecycle(client, admin):
    signup = {"email": "newbuyer@example.com", "password": "LongPassword#1", "full_name": "New Buyer",
              "organization": "Acme Offsets", "purpose": "Buy verified credits"}
    assert client.post("/api/v1/auth/register/buyer", json=signup).status_code == 201
    pending = client.post("/api/v1/auth/login", data={"username": signup["email"], "password": signup["password"]})
    assert pending.status_code == 403 and "awaiting" in pending.json()["detail"]
    apps = client.get("/api/v1/admin/applications", headers=admin).json()
    app = next(a for a in apps if a["applicant"] == signup["email"])
    assert app["type"] == "CREDIT_BUYER" and app["status"] == "PENDING"
    assert client.post(f"/api/v1/admin/applications/{app['application_id']}/review", json={"action": "APPROVE"}, headers=admin).status_code == 200
    buyer2 = login(client, signup["email"], signup["password"])
    assert client.get("/api/v1/credits/summary", headers=buyer2).status_code == 200
    uid = next(u["id"] for u in client.get("/api/v1/admin/accounts", params={"q": "newbuyer"}, headers=admin).json())
    assert client.post(f"/api/v1/admin/accounts/{uid}/status", json={"status": "SUSPENDED"}, headers=admin).status_code == 200
    assert client.post("/api/v1/auth/login", data={"username": signup["email"], "password": signup["password"]}).status_code == 403
    temp = client.post(f"/api/v1/admin/accounts/{uid}/reset-password", headers=admin).json()["temporary_password"]
    client.post(f"/api/v1/admin/accounts/{uid}/status", json={"status": "ACTIVE"}, headers=admin)
    login(client, signup["email"], temp)


def test_company_registration_gets_company_after_approval(client, admin):
    signup = {"email": "ops@newplant.example", "password": "LongPassword#1", "full_name": "New Operator",
              "legal_name": "New Plant Ltd", "state": "Ontario", "city": "Toronto"}
    assert client.post("/api/v1/auth/register/company", json=signup).status_code == 201
    app = next(a for a in client.get("/api/v1/admin/applications", headers=admin).json() if a["applicant"] == signup["email"])
    client.post(f"/api/v1/admin/applications/{app['application_id']}/review", json={"action": "APPROVE"}, headers=admin)
    h = login(client, signup["email"], signup["password"])
    assert client.get("/api/v1/auth/me", headers=h).json()["company_name"] == "New Plant Ltd"
    assert client.get("/api/v1/requests/2026-01", headers=h).status_code == 404  # no dataset yet


def test_login_throttle(client):
    for _ in range(8):
        client.post("/api/v1/auth/login", data={"username": "nobody@x.com", "password": "bad"})
    assert client.post("/api/v1/auth/login", data={"username": "nobody@x.com", "password": "bad"}).status_code == 429
