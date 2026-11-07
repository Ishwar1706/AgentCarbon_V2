import os
import shutil
import tempfile
import time
from pathlib import Path

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
def operator(client):
    return login(client, "northstar@agentcarbon.demo")


def wait_run(client, headers, company, run_id, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        d = client.get(f"/api/v1/verifications/runs/{run_id}", params={"company_id": company}, headers=headers).json()
        if d["status"] in ("COMPLETED", "FAILED"):
            return d
        time.sleep(0.2)
    raise AssertionError("run did not finish")
