from fastapi import APIRouter, Depends, HTTPException, Query
from api.dependencies import get_supabase_client
from api.models.responses import (
    ArticlesResponse, ArticleItem,
    GroupsResponse, GroupItem, GroupArticle,
    GroupDetailResponse,
)

router = APIRouter(prefix="/articles", tags=["Articles"])

SOURCE_NAMES = {1: "news18", 2: "toi", 3: "ht", 4: "indianexpress", 6: "zeenews", 7: "ndtv"}


# ── GET /articles/groups ──────────────────────────────────────────────────────

@router.get("/groups", response_model=GroupsResponse)
def list_groups(
    limit: int = Query(20, ge=1, le=100),
    page: int = Query(1, ge=1),
    active_only: bool = Query(True),
    sb=Depends(get_supabase_client),
):
    """List article groups (clustered topics). Primary editorial endpoint.
    Ordered by last_updated_at DESC. Includes a preview of member articles.
    """
    # Build base query
    query = sb.table("article_groups").select("*", count="exact")

    if active_only:
        query = query.gt("expires_at", "now()")

    query = query.order("last_updated_at", desc=True)

    # Pagination
    offset = (page - 1) * limit
    result = query.range(offset, offset + limit - 1).execute()

    groups = []
    for g in result.data:
        group_id = g["id"]

        # Fetch top 3 articles as preview
        articles_result = (
            sb.table("articles")
            .select("id, title, source_id, group_id, url_loc, publication_date")
            .eq("group_id", group_id)
            .order("id", desc=True)
            .limit(3)
            .execute()
        )

        preview = [
            GroupArticle(
                id=a["id"],
                title=a.get("title"),
                url_loc=a.get("url_loc"),
                source=SOURCE_NAMES.get(a.get("source_id"), str(a.get("source_id"))),
                group_id=a.get("group_id"),
                publication_date=a.get("publication_date"),
            )
            for a in articles_result.data
        ]

        topic_label = preview[0].title if preview and preview[0].title else ""

        groups.append(GroupItem(
            group_id=group_id,
            topic_label=topic_label,
            article_count=g.get("article_count", 0),
            last_updated_at=g.get("last_updated_at"),
            expires_at=g.get("expires_at"),
            articles=preview,
        ))

    total = result.count if result.count is not None else len(groups)

    return GroupsResponse(groups=groups, total=total, page=page, limit=limit)


# ── GET /articles/groups/{group_id} ──────────────────────────────────────────

@router.get("/groups/{group_id}", response_model=GroupDetailResponse)
def get_group(group_id: int, sb=Depends(get_supabase_client)):
    """Fetch one group + all its member articles."""
    # Fetch group
    group_result = (
        sb.table("article_groups")
        .select("*")
        .eq("id", group_id)
        .limit(1)
        .execute()
    )

    if not group_result.data:
        raise HTTPException(status_code=404, detail=f"Group {group_id} not found")

    g = group_result.data[0]

    # Fetch all articles in this group
    articles_result = (
        sb.table("articles")
        .select("id, title, url_loc, source_id, group_id, publication_date")
        .eq("group_id", group_id)
        .order("id", desc=True)
        .execute()
    )

    articles = [
        GroupArticle(
            id=a["id"],
            title=a.get("title"),
            url_loc=a.get("url_loc"),
            source=SOURCE_NAMES.get(a.get("source_id"), str(a.get("source_id"))),
            group_id=a.get("group_id"),
            publication_date=a.get("publication_date"),
        )
        for a in articles_result.data
    ]
    
    topic_label = articles[0].title if articles and articles[0].title else ""

    return GroupDetailResponse(
        group_id=g["id"],
        topic_label=topic_label,
        article_count=g.get("article_count", 0),
        last_updated_at=g.get("last_updated_at"),
        expires_at=g.get("expires_at"),
        articles=articles,
    )


# ── GET /articles ─────────────────────────────────────────────────────────────

@router.get("", response_model=ArticlesResponse)
def list_articles(
    limit: int = Query(20, ge=1, le=100),
    page: int = Query(1, ge=1),
    source: str | None = Query(None, description="Filter by source key (e.g. 'news18')"),
    group_id: int | None = Query(None, description="Filter by group ID"),
    from_date: str | None = Query(None, description="Filter articles published after this date (ISO format)"),
    sb=Depends(get_supabase_client),
):
    """Query saved articles with filtering. Secondary endpoint for debugging."""
    query = (
        sb.table("articles")
        .select("id, title, url_loc, source_id, group_id, publication_date, image_loc", count="exact")
    )

    # Apply filters
    if source:
        source_id_map = {v: k for k, v in SOURCE_NAMES.items()}
        sid = source_id_map.get(source)
        if sid is None:
            raise HTTPException(status_code=400, detail=f"Unknown source: {source}")
        query = query.eq("source_id", sid)

    if group_id is not None:
        query = query.eq("group_id", group_id)

    if from_date:
        query = query.gte("publication_date", from_date)

    query = query.order("id", desc=True)

    # Pagination
    offset = (page - 1) * limit
    result = query.range(offset, offset + limit - 1).execute()

    articles = [
        ArticleItem(
            id=a["id"],
            title=a.get("title"),
            url_loc=a.get("url_loc"),
            source_id=a.get("source_id"),
            group_id=a.get("group_id"),
            publication_date=a.get("publication_date"),
            image_loc=a.get("image_loc"),
        )
        for a in result.data
    ]

    total = result.count if result.count is not None else len(articles)

    return ArticlesResponse(articles=articles, total=total, page=page, limit=limit)
