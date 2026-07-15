import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.utils.fx import ensure_updated
from backend.routers import admin, auth, benchmarks, billing, connectors, historical_imports, holdings, internal, portfolio

_default_origins = "http://localhost:5173,http://127.0.0.1:5173"
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", _default_origins).split(",")


def _refresh_fx_background():
    try:
        ensure_updated()
    except Exception:
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Refresh FX in the background so startup readiness is not gated on the
    # yfinance network call. On Cloud Run (scale-to-zero) a blocking fetch here
    # inflates cold-start latency past the client login timeout.
    threading.Thread(target=_refresh_fx_background, daemon=True).start()
    yield


app = FastAPI(title="Portfolio Tracking API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth")
app.include_router(portfolio.router, prefix="/api/portfolio")
app.include_router(benchmarks.router, prefix="/api/benchmarks")
app.include_router(holdings.router, prefix="/api/holdings")
app.include_router(connectors.router, prefix="/api/connectors")
app.include_router(historical_imports.router, prefix="/api/connectors")
app.include_router(admin.router, prefix="/api/admin")
app.include_router(internal.router, prefix="/api/internal")
app.include_router(billing.router, prefix="/api/billing")


@app.get("/health")
def health():
    return {"status": "ok"}
