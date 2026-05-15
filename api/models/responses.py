from pydantic import BaseModel


# ── Health ────────────────────────────────────────────────────────────────────

class HealthChecks(BaseModel):
    database: str
    cohere_key_present: bool

class HealthResponse(BaseModel):
    status: str
    checks: HealthChecks
    version: str
    timestamp: str


# ── Pipeline Run ──────────────────────────────────────────────────────────────

class SourceStats(BaseModel):
    fetched: int = 0
    inserted: int = 0
    skipped: int = 0
    errors: int = 0

class RunSummary(BaseModel):
    total_fetched: int = 0
    total_inserted: int = 0
    total_skipped_duplicate: int = 0
    total_errors: int = 0
    new_groups_created: int = 0
    articles_grouped: int = 0

class PipelineRunResponse(BaseModel):
    run_id: str
    started_at: str
    finished_at: str
    duration_seconds: float
    sources_processed: list[str]
    sources_failed: list[str]
    summary: RunSummary
    log_file: str
    per_source: dict[str, SourceStats]


# ── Pipeline Runs List ────────────────────────────────────────────────────────

class RunEntry(BaseModel):
    run_id: str
    log_file: str
    size_bytes: int

class RunsListResponse(BaseModel):
    runs: list[RunEntry]
    total: int


# ── Articles ──────────────────────────────────────────────────────────────────

class ArticleItem(BaseModel):
    id: int
    title: str | None = None
    url_loc: str | None = None
    source_id: int | None = None
    group_id: int | None = None
    publication_date: str | None = None
    image_loc: str | None = None

class ArticlesResponse(BaseModel):
    articles: list[ArticleItem]
    total: int
    page: int
    limit: int


# ── Groups ────────────────────────────────────────────────────────────────────

class ArticlePreview(BaseModel):
    title: str | None = None
    source_id: int | None = None
    url_loc: str | None = None
    publication_date: str | None = None

class GroupItem(BaseModel):
    group_id: int
    article_count: int
    last_updated_at: str | None = None
    expires_at: str | None = None
    group_keywords: list[str] | None = None
    articles_preview: list[ArticlePreview] = []

class GroupsResponse(BaseModel):
    groups: list[GroupItem]
    total: int
    page: int
    limit: int

class GroupDetailResponse(BaseModel):
    group_id: int
    article_count: int
    last_updated_at: str | None = None
    expires_at: str | None = None
    group_keywords: list[str] | None = None
    articles: list[ArticleItem] = []
