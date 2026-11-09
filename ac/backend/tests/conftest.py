import os
import shutil
import tempfile
import time

_tmp = tempfile.mkdtemp(prefix="agentcarbon-test-")
os.environ.update(
    DATABASE_URL=f"sqlite:///{_tmp}/test.db", DATA_DIR=f"{_tmp}/data", UPLOAD_DIR=f"{_tmp}/uploads",
    REPORT_DIR=f"{_tmp}/reports", GROQ_API_KEY="", DEMO_MODE="true", DEMO_PASSWORD="Demo@12345",
    GROQ_CALL_DELAY_SECONDS="0",
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c
    shutil.rmtree(_tmp, ignore_errors=True)


def login(client, email, password="Demo@12345"):
    r = client.post("/api/v1/auth/login", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def auditor(client):
    return login(client, "auditor@agentcarbon.demo")


@pytest.fixture(scope="session")
def operator(client):  # Northstar Mobility Works
    return login(client, "northstar@agentcarbon.demo")


@pytest.fixture(scope="session")
def buyer(client):
    return login(client, "buyer@agentcarbon.demo")


@pytest.fixture(scope="session")
def admin(client):
    return login(client, "admin@agentcarbon.demo")


def wait_run(client, headers, company, run_id, timeout=40):
    end = time.time() + timeout
    while time.time() < end:
        d = client.get(f"/api/v1/verifications/runs/{run_id}", params={"company_id": company}, headers=headers).json()
        if d["status"] in ("COMPLETED", "FAILED"):
            return d
        time.sleep(0.2)
    raise AssertionError("run did not finish")


def run_verification(client, headers, company, period, mode="DETERMINISTIC"):
    r = client.post("/api/v1/verifications/run", params={"company_id": company},
                    json={"period": period, "mode": mode}, headers=headers)
    assert r.status_code == 202, r.text
    d = wait_run(client, headers, company, r.json()["run_id"])
    assert d["status"] == "COMPLETED", d
    return d


def submit_month(client, op_headers, period):
    """Operator opens the month, keeps the plant's prefilled figures and submits."""
    detail = client.get(f"/api/v1/requests/{period}", headers=op_headers).json()
    assert detail["available"], detail
    pre = detail["prefill"]
    body = {"expected_credits_tco2e": pre["expected_credits_tco2e"], "declared_electricity_kwh": pre["electricity_kwh"],
            "declared_production_units": pre["production_units"], "declared_natural_gas_scm": pre["natural_gas_scm"],
            "declared_diesel_litres": pre["diesel_litres"], "notes": "test"}
    assert client.put(f"/api/v1/requests/{period}", json=body, headers=op_headers).status_code == 200
    r = client.post(f"/api/v1/requests/{period}/submit", headers=op_headers)
    assert r.status_code == 200, r.text
    return body


def upload(client, op_headers, period, doc_type, content, info_request_id="", name="doc.pdf"):
    return client.post("/api/v1/documents/upload", headers=op_headers,
                       data={"period": period, "document_type": doc_type, "info_request_id": info_request_id},
                       files={"file": (name, content, "application/pdf")})
