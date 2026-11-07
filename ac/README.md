# AgentCarbon

Sensor-backed, multi-agent pre-verification of monthly industrial carbon claims.

**To run it: read `RUN_GUIDE.md`.**

## What it does

1. **Simulated sensor fleets, different per company.** Five synthetic automotive plants run SCD40-style CO₂/temperature/humidity sensors: Northstar 5, Ironwood 4, Crestline 3, Redwood 6, Summit 8 (26 in total), placed in paint, body, press, assembly and utilities zones. Each has 5 months of 15-minute history (≈ 374,000 readings) plus planted faults (stuck values, drift, spikes, dropouts).
2. **Readings become complete monthly data.** Raw readings roll up per sensor and per month (completeness, anomalies, drift against peer sensors, trust and health). A finished 30-day period is **sealed** with a SHA-256 hash. A live simulator keeps adding readings on a simulated clock (+15 min per tick) and seals month 6, 7, … automatically.
3. **Meter trust engine.** Four electricity meters are fused; the main meter is down-weighted when it deviates from the others, so manipulated readings stop influencing the verified total.
4. **Agentic verification (Groq, `openai/gpt-oss-120b`).** Four specialist agents (claim validation, evidence assessment, trust & fraud, compliance) assess the company-specific evidence packet independently, then **debate** (challenges and rebuttals), and a consensus agent proposes a recommendation. A deterministic **safety guard** may only make the recommendation *stricter*, never more lenient. A human auditor records the final decision.
5. **Audit registry.** Finalised claims are written to an append-only **hash-chained ledger**; reports can be exported as HTML/JSON and verified for tampering. (Local tamper-evident ledger — not a public blockchain.)

## Roles
Plant operator (own company only) · Auditor (admin-verified) · Regulator viewer (read-only) · Admin (approves companies/auditors).

## What changed from the first version (fixes)

| Area | Before | Now |
|---|---|---|
| Agent Debate / Audit pages | Returned 400 for auditors, hardcoded `CLAIM-2026-0N` | Company-aware everywhere |
| Company bundles | Verification, decisions, reports, registry returned 404 | All five companies fully supported |
| Company isolation | Claims, runs, reports and documents addressable across companies | One access resolver; every claim/run/document is checked against the company |
| Data | All five companies had identical data | Different claim gaps, calibration validity, sensor counts and faults |
| Sensor data | One global simulator posting to a non-existent sensor | Per-company fleets in the database, rolled up into sealed monthly datasets, feeding the agents |
| Sensor ingest | Unauthenticated | Per-sensor API key (`X-Sensor-Key`) |
| AI | Rule-based "agents"; LLM only reworded text; ground-truth labels leaked to the prompt | Real LLM agents + debate + consensus, guard floor, no ground-truth leaks, background runs with live progress, fallback if the API fails |
| Calibration evidence | Calendar-month filter missed certificates; any certificate counted | Certificate must cover the whole period for the main meter |
| Recommendation logic | Missing calibration outranked a severe discrepancy; no reject outcome | Severity-ordered; `RECOMMEND_REJECTION` exists |
| Registry | Random fake hash; false "tampered" after any new decision | Hash-chained records over an immutable snapshot |
| Security | `change-me` JWT default, hardcoded demo passwords, no login throttle, unrestricted uploads | Random persisted secret, `DEMO_MODE` switch, login throttling, upload whitelist + content check |
| Trust engine | Slow row-by-row loop | ~10× faster, cached |
| Setup | Docker/Postgres required | `python run.py` with SQLite (Postgres optional) |
| UI | Dark/bright | Soft light theme |

## What is real / what is simulated
* **Simulated:** all company data, meter readings, claims and SCD40 sensor readings, and the planted faults. Labelled as synthetic in the UI.
* **Real:** the trust engine, rollups, rules, agent orchestration, guard, registry hashing, access control.
* The Groq integration was tested against a mocked Groq endpoint (9 calls, guard override, fallback). It has **not** been exercised against the live Groq API from the build environment; the first run with your key is the real test (see RUN_GUIDE troubleshooting).

## Layout
```
run.py                  start everything
backend/app/            FastAPI app (api/, models/, services/, agents/)
backend/tests/          12 end-to-end tests
frontend/src/           React UI (frontend/dist is pre-built)
datasets/generated/     synthetic source data + per-company bundles
```
