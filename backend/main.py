from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routers import portfolio, benchmarks, holdings

app = FastAPI(title="Portfolio Tracking API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(portfolio.router, prefix="/api/portfolio")
app.include_router(benchmarks.router, prefix="/api/benchmarks")
app.include_router(holdings.router, prefix="/api/holdings")


@app.get("/health")
def health():
    return {"status": "ok"}
