import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.utils.fx import ensure_updated
from backend.routers import auth, benchmarks, connectors, historical_imports, holdings, portfolio

_default_origins = "http://localhost:5173,http://127.0.0.1:5173"
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", _default_origins).split(",")


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_updated()
    yield


app = FastAPI(title="Portfolio Tracking API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth")
app.include_router(portfolio.router, prefix="/api/portfolio")
app.include_router(benchmarks.router, prefix="/api/benchmarks")
app.include_router(holdings.router, prefix="/api/holdings")
app.include_router(connectors.router, prefix="/api/connectors")
app.include_router(historical_imports.router, prefix="/api/connectors")


@app.get("/health")
def health():
    return {"status": "ok"}
