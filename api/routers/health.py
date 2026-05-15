import os
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Response
from api.dependencies import get_supabase_client
from api.models.responses import HealthResponse, HealthChecks

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
def health_check(response: Response, sb=Depends(get_supabase_client)):
    """Liveness + readiness check for scheduler/load balancer."""
    db_status = "ok"
    try:
        # Cheap query to verify Supabase connectivity
        sb.table("sources").select("id").limit(1).execute()
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
