from pydantic import BaseModel, Field


class PipelineRunRequest(BaseModel):
    """Request body for POST /api/v1/pipeline/run"""
    sources: list[str] | None = Field(
        default=None,
        description="Source keys to process. Defaults to ALL configured sources."
    )
    limit: int = Field(
        default=10,
        ge=1, le=50,
        description="Max articles to fetch per source."
    )
