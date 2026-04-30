from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def portfolio_health():
    return {"status": "ok", "router": "portfolio"}
