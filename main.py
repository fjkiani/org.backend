"""
CrisPRO.org — Thin FastAPI Backend.

Auto-discovers capability routers from backend/capabilities/.
To add a new capability: create capabilities/my_thing/router.py with
  router = APIRouter(prefix="/api/v1/my-thing")
Restart — it's wired in.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from config import MODEL_VERSION
from capabilities import discover_routers

# ── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("crispro")


# ── Lifespan (startup/shutdown) ──────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load all capability-specific data before serving."""
    # Platinum Window reference data
    from capabilities.platinum_window.router import load_reference
    load_reference()
    logger.info("✅ Platinum Window reference data loaded")

    # Progression Arbiter model
    from capabilities.progression_arbiter.router import load_model
    load_model()
    logger.info("✅ Progression Arbiter model loaded")

    yield


# ── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="CrisPRO.org API",
    description="Precision Oncology for the 90% — Clinical Decision Support Backend",
    version=MODEL_VERSION,
    lifespan=lifespan,
)

# CORS — permissive for dev; restrict in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:4173",
        "https://crispro.org",
        "https://www.crispro.org"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting
from capabilities.platinum_window.router import limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ── Auto-register capability routers ─────────────────────────────────────────

for router in discover_routers():
    app.include_router(router)
    logger.info(f"  → Registered: {router.prefix}")


# ── Debug Diagnostic ─────────────────────────────────────────────────────────

@app.get("/debug/artifacts")
def debug_artifacts():
    import os
    from pathlib import Path
    
    current_dir = Path(__file__).resolve().parent
    results = {}
    
    # Check Platinum Window
    pw_path = current_dir / "capabilities" / "platinum_window" / "artifacts"
    results["platinum_window"] = {
        "exists": pw_path.exists(),
        "abs_path": str(pw_path),
        "files": [str(p.relative_to(pw_path)) for p in pw_path.rglob("*") if p.is_file()] if pw_path.exists() else []
    }
    
    # Check Progression Arbiter
    pa_path = current_dir / "capabilities" / "progression_arbiter" / "artifacts"
    results["progression_arbiter"] = {
        "exists": pa_path.exists(),
        "abs_path": str(pa_path),
        "files": [str(p.relative_to(pa_path)) for p in pa_path.rglob("*") if p.is_file()] if pa_path.exists() else []
    }
    
    return results


# ── Health ───────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": MODEL_VERSION,
        "capabilities": [r.prefix for r in discover_routers()],
    }
