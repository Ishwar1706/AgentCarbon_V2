import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.api import admin, audit_registry, auditor, auth, claims, companies, dashboard, documents, sensors, simulation, verifications
from app.core.config import PROJECT_ROOT, settings
from app.core.database import Base, SessionLocal, engine
from app.services.company_trust_service import get_company_trust_analysis
from app.services.live_engine import engine as live_engine
from app.services.provisioning import provision_all

import app.models  # noqa: F401  (register tables)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("agentcarbon")


def _warm_caches() -> None:
    from app.services.company_data import COMPANY_IDS
    for company_id in sorted(COMPANY_IDS):
        try:
            get_company_trust_analysis(company_id)
        except Exception:
            log.exception("trust warm-up failed for %s", company_id)


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    if settings.seed_on_startup:
        with SessionLocal() as db:
            provision_all(db)
    threading.Thread(target=_warm_caches, daemon=True).start()
    log.info("AgentCarbon ready. Groq configured: %s (model %s)", settings.groq_configured, settings.groq_model)
    yield
    live_engine.shutdown()


app = FastAPI(title=settings.app_name, version="2.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_list, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health():
    return {"status": "ok", "groq_configured": settings.groq_configured, "model": settings.groq_model}


for module in (auth, admin, companies, dashboard, sensors, simulation, claims, verifications,
               documents, auditor, audit_registry):
    app.include_router(module.router, prefix="/api/v1")

# Optional single-port mode: serve the built frontend (frontend/dist) from the API.
DIST = PROJECT_ROOT / "frontend" / "dist"
if DIST.is_dir():
    from fastapi.staticfiles import StaticFiles

    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        target = (DIST / path).resolve()
        if path and target.is_file() and DIST in target.parents:
            return FileResponse(target)
        return FileResponse(DIST / "index.html")
