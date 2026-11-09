# AgentCarbon — Run Guide

Everything you need to start the finished system. Allow about 10 minutes the first time.

## 1. What you need installed

| Tool | Version | Needed for |
|---|---|---|
| Python | 3.10 or newer | the backend (required) |
| Node.js | 18 or newer | **only** if you want to edit/rebuild the UI (optional — a built UI is already included) |
| A Groq API key | — | the AI agents (get one free at https://console.groq.com/keys) |

No database server is needed. The system uses a built-in SQLite file.

## 2. First-time setup (3 commands)

Open a terminal in the project folder (the one that contains `run.py`).

**Windows (PowerShell)**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
copy .env.example .env
```
**macOS / Linux**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env
```

## 3. Add your Groq API key

Open the file `.env` in any text editor and fill in one line:

```
GROQ_API_KEY=gsk_your_key_here
```

Nothing else is required. (Without a key the system still runs, using the rule engine only; the AI debate is switched off and the top bar shows "RULES ONLY".)

## 4. Start it

```bash
python run.py
```
Wait ~20–30 seconds on the **first** start. It is simulating five months of sensor readings for every company. When you see `Application startup complete`, open:

**http://localhost:8000**

To stop: press `Ctrl + C`. Your data is kept in `data/agentcarbon.db`.
After changing backend files, stop and restart `python run.py`. After changing frontend source, run `cd frontend && npm run build`, then restart the app.
To start from scratch, stop the app and remove the database and generated company bundles; keep the source dataset and generated base CSVs:

```bash
rm -f data/agentcarbon.db data/agentcarbon.db-shm data/agentcarbon.db-wal
rm -rf datasets/generated/company_bundles
find uploads reports -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
python run.py
```

## 5. Demo accounts

All demo accounts use the password **`Demo@12345`** (change it with `DEMO_PASSWORD` in `.env`). On the login page you can click an account to fill it in.

| Account | Role | What it can do |
|---|---|---|
| `auditor@agentcarbon.demo` | Auditor | Run AI verification, record decisions, verify documents, register in the audit registry |
| `buyer@agentcarbon.demo` | Credit buyer | View and verify auditor-approved, registry-registered credits |
| `northstar@agentcarbon.demo` | Operator (5 sensors) | Control the live sensor simulator, submit claims, upload evidence |
| `ironwood@agentcarbon.demo` | Operator (4 sensors) | same, for Ironwood Automotive |
| `crestline@agentcarbon.demo` | Operator (3 sensors) | same, for Crestline Motors |
| `redwood@agentcarbon.demo` | Operator (6 sensors) | same, for Redwood Vehicle Systems |
| `summit@agentcarbon.demo` | Operator (8 sensors) | same, for Summit Auto Works |
| `admin@agentcarbon.demo` | Admin | Approve new companies and auditors |

## 6. Suggested demo walk-through (about 8 minutes)

1. **Sign in as `northstar@agentcarbon.demo`** → *Sensors & Monthly Data*.
   You see 5 sensors, 5 sealed months of readings, per-sensor health, charts, raw readings and a CSV export.
2. In **Live sensor simulator**: click **Start live feed**. Watch the *Live ticker* fill and *Month 6* progress grow. Inject a fault (e.g. `STUCK` on a sensor) and click **+1 day**; the sensor becomes flagged. Click **Complete & seal month 6** — the month becomes a complete, hash-sealed monthly dataset.
3. *Monthly Request* → save a draft and submit the month when ready. An auditor can run agents on any month with data, even before submission; without a submitted request, agents use the plant's dataset figures. Decisions, information requests and registry registration still require submission.
4. **Sign out, sign in as `auditor@agentcarbon.demo`**, pick a company at the top (each has a different number of sensors and a different story).
5. *Review & Agents* → choose any data month → **Run verification**. Watch the live progress log while the four agents assess, debate and a consensus agent decides. Read the assessments, the debate transcript and the evidence packet.
6. After the operator submits, record an **Auditor decision**, then *Audit Registry* → **Register**, then **Verify**. Open the HTML report.

Try Month 4 (major under-reporting) vs Month 1 (clean), and Crestline Motors months 4–5 (calibration certificate expired → "additional evidence required").

## 7. Tuning the AI agents (`.env`)

| Setting | Meaning |
|---|---|
| `GROQ_REASONING_EFFORT` | `low` (fast, default), `medium`, `high` (deeper, slower, more tokens) |
| `AGENT_DEBATE_ROUNDS` | `1` = full debate (9 model calls per verification); `0` = skip the rebuttal round (5 calls) |
| `GROQ_CALL_DELAY_SECONDS` | pause between calls; raise to `5`–`10` on a free tier |

A full debate uses roughly 25–40k tokens. If Groq answers "rate limit", the app waits and retries automatically — a run can then take a few minutes. If the AI cannot be reached at all, the run falls back to the rule engine and says so (`DETERMINISTIC_FALLBACK`).

## 8. Editing the UI (optional)

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173 , talks to the API on :8000
npm run build    # rebuilds frontend/dist, served by run.py
```

## 9. Running the tests (optional)

```bash
cd backend
python -m pytest
```

## 10. Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError` | The virtual environment is not active, or `pip install -r backend/requirements.txt` was skipped |
| Port 8000 busy | `PORT=8001 python run.py` (Windows PowerShell: `$env:PORT=8001; python run.py`) |
| Top bar says "RULES ONLY" | `GROQ_API_KEY` is empty/misspelled in `.env`; restart after editing |
| Run ends as `DETERMINISTIC_FALLBACK` | Open the run: the progress log shows why (wrong key, no internet, rate limit) |
| Blank page after code changes | `cd frontend && npm run build` |
| Want a clean slate | Stop the app and use the database/company-bundle reset commands in section 4; preserve `datasets/source/` and `datasets/generated/*.csv` |

## 11. Before using this for anything real

* Set `DEMO_MODE=false`, then create real users: `python backend/scripts/create_user.py you@company.com "Your Name" ADMIN`
* Run behind HTTPS (a reverse proxy such as Nginx/Caddy) and use PostgreSQL via `DATABASE_URL` for multi-user load.
* Run **one** worker process only (the live simulator and agent runner live inside it).
* All company, meter and sensor data here is **synthetic**. See README.md → "What is real / what is simulated".
