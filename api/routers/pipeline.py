import json
import os
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from api.dependencies import get_supabase_client
from api.models.requests import PipelineRunRequest
from api.models.responses import (
    PipelineRunResponse, RunSummary, SourceStats,
    RunsListResponse, RunEntry,
)
from fetchers import news18, toi, zeenews, ht, indianexpress, ndtv
from pipeline.embed import embed_text, build_embed_input
from pipeline.db import (
    url_exists, build_jaccard_keywords,
    find_matching_group, update_group, create_group, insert_article,
)

SOURCES = {
    "news18": news18,
    "toi":    toi,
    "ht":     ht,
    "indianexpress": indianexpress,
    "zeenews": zeenews,
    "ndtv":    ndtv,
}

LOGS_DIR = Path("logs")

router = APIRouter(prefix="/pipeline", tags=["Pipeline"])


# ── POST /pipeline/run ────────────────────────────────────────────────────────

def _process_article(sb, article: dict, source_key: str, run_report: list) -> str:
    """Process one article. Returns action: 'inserted', 'skipped', or raises."""
    url = article.get("url_loc")
    if not url:
        return "skipped"

    if url_exists(sb, url):
        return "skipped"

    embedding   = embed_text(build_embed_input(article))
    jaccard_kws = build_jaccard_keywords(article)

    group_id, debug_data = find_matching_group(sb, jaccard_kws, embedding)

    action = "new_group"
    if group_id:
        update_group(sb, group_id, jaccard_kws)
        action = "grouped"
    else:
        group_id = create_group(sb, embedding, jaccard_kws)

    insert_article(sb, article, source_key, embedding, jaccard_kws, group_id)

    run_report.append({
        "article": {
            "title": article.get("news", {}).get("title"),
            "url": url,
            "source": source_key,
            "extracted_keywords": jaccard_kws,
        },
        "scoring": debug_data,
        "final_action": action,
        "assigned_id": group_id,
    })

    return action


@router.post("/run", response_model=PipelineRunResponse)
def run_pipeline(body: PipelineRunRequest = PipelineRunRequest(), sb=Depends(get_supabase_client)):
    """Main trigger — runs the full extraction pipeline.
    This is the endpoint the scheduler calls every X minutes.
    """
    started_at = datetime.now(timezone.utc)
    run_id = started_at.strftime("%Y%m%d_%H%M%S")
    run_report: list[dict] = []

    # Resolve which sources to run
    requested = body.sources or list(SOURCES.keys())
    invalid = [s for s in requested if s not in SOURCES]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Unknown sources: {invalid}")

    sources_processed = []
    sources_failed = []
    per_source: dict[str, SourceStats] = {}
    summary = RunSummary()

    for source_key in requested:
        fetcher = SOURCES[source_key]
        stats = SourceStats()
        try:
            articles = fetcher.fetch_sitemap(limit=body.limit)
            stats.fetched = len(articles)
        except Exception:
            sources_failed.append(source_key)
            per_source[source_key] = stats
            continue

        sources_processed.append(source_key)

        for article in articles:
            try:
                action = _process_article(sb, article, source_key, run_report)
                if action == "skipped":
                    stats.skipped += 1
                elif action == "new_group":
                    stats.inserted += 1
                    summary.new_groups_created += 1
                elif action == "grouped":
                    stats.inserted += 1
                    summary.articles_grouped += 1
            except Exception:
                stats.errors += 1

        per_source[source_key] = stats
        summary.total_fetched += stats.fetched
        summary.total_inserted += stats.inserted
        summary.total_skipped_duplicate += stats.skipped
        summary.total_errors += stats.errors

    # Save log file (preserves existing behaviour)
    LOGS_DIR.mkdir(exist_ok=True)
    log_filename = f"{run_id}.json"
    log_path = LOGS_DIR / log_filename
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(run_report, f, indent=2, ensure_ascii=False)

    finished_at = datetime.now(timezone.utc)

    return PipelineRunResponse(
        run_id=run_id,
        started_at=started_at.isoformat(),
        finished_at=finished_at.isoformat(),
        duration_seconds=round((finished_at - started_at).total_seconds(), 2),
        sources_processed=sources_processed,
        sources_failed=sources_failed,
        summary=summary,
        log_file=str(log_path),
        per_source=per_source,
    )


# ── GET /pipeline/runs ────────────────────────────────────────────────────────

@router.get("/runs", response_model=RunsListResponse)
def list_runs(limit: int = 10, page: int = 1):
    """List recent run logs (reads the logs/ directory)."""
    LOGS_DIR.mkdir(exist_ok=True)
    all_logs = sorted(LOGS_DIR.glob("*.json"), reverse=True)
    total = len(all_logs)

    start = (page - 1) * limit
    page_logs = all_logs[start : start + limit]

    runs = []
    for p in page_logs:
        run_id = p.stem  # e.g. "20260515_100000"
        runs.append(RunEntry(
            run_id=run_id,
            log_file=str(p),
            size_bytes=p.stat().st_size,
        ))

    return RunsListResponse(runs=runs, total=total)


# ── GET /pipeline/runs/{run_id} ──────────────────────────────────────────────

@router.get("/runs/{run_id}")
def get_run(run_id: str):
    """Fetch the full JSON run report for a specific run."""
    log_path = LOGS_DIR / f"{run_id}.json"
    if not log_path.exists():
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    with open(log_path, "r", encoding="utf-8") as f:
        return json.load(f)
