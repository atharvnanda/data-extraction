import os
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Response
from api.dependencies import get_db_connection
from api.models.responses import HealthResponse, HealthChecks

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
def health_check(response: Response, conn=Depends(get_db_connection)):
    """Liveness + readiness check for scheduler/load balancer."""
    db_status = "ok"
    try:
        # Cheap query to verify DB connectivity
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
    except Exception as e:
        db_status = f"error: {e}"

    cohere_present = bool(os.environ.get("COHERE_API_KEY"))

    if db_status == "ok" and cohere_present:
        status = "healthy"
    elif db_status == "ok" or cohere_present:
        status = "degraded"
    else:
        status = "unhealthy"
        response.status_code = 503

    return HealthResponse(
        status=status,
        checks=HealthChecks(database=db_status, cohere_key_present=cohere_present),
        version="1.0.0",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
