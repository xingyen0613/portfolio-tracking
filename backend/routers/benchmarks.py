from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def benchmarks_health():
    return {"status": "ok", "router": "benchmarks"}
