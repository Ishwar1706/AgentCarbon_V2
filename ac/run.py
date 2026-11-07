"""Start AgentCarbon (API + pre-built web app) on http://localhost:8000"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT)

if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    print(f"\n  AgentCarbon starting on http://{host}:{port}")
    print("  (the first start takes ~20 s while five months of sensor data are simulated)\n")
    # One worker only: the live sensor simulator and the agent runner live inside this process.
    uvicorn.run("app.main:app", host=host, port=port, workers=1)
