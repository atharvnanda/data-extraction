from fastapi import APIRouter, Depends, HTTPException, Query
from api.dependencies import get_db_connection
from api.models.responses import (
    ArticlesResponse, ArticleItem,
    GroupsResponse, GroupItem, GroupArticle,
    GroupDetailResponse,
)

router = APIRouter(prefix="/articles", tags=["Articles"])

SOURCE_NAMES = {1: "news18", 2: "toi", 3: "ht", 4: "indianexpress", 6: "zeenews", 7: "ndtv"}


import psycopg2.extras

# ── GET /articles/groups ──────────────────────────────────────────────────────

@router.get("/groups", response_model=GroupsResponse)
def list_groups(
    limit: int = Query(20, ge=1, le=100),
    page: int = Query(1, ge=1),
    active_only: bool = Query(True),
    conn=Depends(get_db_connection),
):
    """List article groups (clustered topics). Primary editorial endpoint.
    Ordered by last_updated_at DESC. Includes a preview of member articles.
    """
    offset = (page - 1) * limit

    # Build WHERE clause
    where_clause = "WHERE expires_at > now()" if active_only else ""

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        # Get total count
        cur.execute(f"SELECT COUNT(*) as count FROM article_groups {where_clause}")
        total = cur.fetchone()["count"]

        # Get groups with pagination
        cur.execute(f"""
            SELECT * FROM article_groups 
            {where_clause} 
            ORDER BY last_updated_at DESC 
            LIMIT %s OFFSET %s
        """, (limit, offset))
        result_groups = cur.fetchall()

        groups = []
        for g in result_groups:
            group_id = g["id"]

            # Fetch top 3 articles as preview
            cur.execute("""
                SELECT id, title, source_id, group_id, url_loc, publication_date
                FROM articles
                WHERE group_id = %s
                ORDER BY id DESC
                LIMIT 3
            """, (group_id,))
            articles_data = cur.fetchall()

            preview = [
                GroupArticle(
                    id=a["id"],
                    title=a.get("title"),
                    url_loc=a.get("url_loc"),
                    source=SOURCE_NAMES.get(a.get("source_id"), str(a.get("source_id"))),
                    group_id=a.get("group_id"),
                    publication_date=a.get("publication_date").isoformat() if a.get("publication_date") else None,
                )
                for a in articles_data
            ]

            topic_label = preview[0].title if preview and preview[0].title else ""

            groups.append(GroupItem(
                group_id=group_id,
                topic_label=topic_label,
                article_count=g.get("article_count", 0),
                last_updated_at=g.get("last_updated_at").isoformat() if g.get("last_updated_at") else None,
                expires_at=g.get("expires_at").isoformat() if g.get("expires_at") else None,
                articles=preview,
            ))

    return GroupsResponse(groups=groups, total=total, page=page, limit=limit)


# ── GET /articles/groups/{group_id} ──────────────────────────────────────────

@router.get("/groups/{group_id}", response_model=GroupDetailResponse)
def get_group(group_id: int, conn=Depends(get_db_connection)):
    """Fetch one group + all its member articles."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        # Fetch group
        cur.execute("SELECT * FROM article_groups WHERE id = %s", (group_id,))
        g = cur.fetchone()

        if not g:
            raise HTTPException(status_code=404, detail=f"Group {group_id} not found")

        # Fetch all articles in this group
        cur.execute("""
            SELECT id, title, url_loc, source_id, group_id, publication_date
            FROM articles
            WHERE group_id = %s
            ORDER BY id DESC
        """, (group_id,))
        articles_data = cur.fetchall()

    articles = [
        GroupArticle(
            id=a["id"],
            title=a.get("title"),
            url_loc=a.get("url_loc"),
            source=SOURCE_NAMES.get(a.get("source_id"), str(a.get("source_id"))),
            group_id=a.get("group_id"),
            publication_date=a.get("publication_date").isoformat() if a.get("publication_date") else None,
        )
        for a in articles_data
    ]
    
    topic_label = articles[0].title if articles and articles[0].title else ""

    return GroupDetailResponse(
        group_id=g["id"],
        topic_label=topic_label,
        article_count=g.get("article_count", 0),
        last_updated_at=g.get("last_updated_at").isoformat() if g.get("last_updated_at") else None,
        expires_at=g.get("expires_at").isoformat() if g.get("expires_at") else None,
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
    conn=Depends(get_db_connection),
):
    """Query saved articles with filtering. Secondary endpoint for debugging."""
    conditions = []
    params = []

    if source:
        source_id_map = {v: k for k, v in SOURCE_NAMES.items()}
        sid = source_id_map.get(source)
        if sid is None:
            raise HTTPException(status_code=400, detail=f"Unknown source: {source}")
        conditions.append("source_id = %s")
        params.append(sid)

    if group_id is not None:
        conditions.append("group_id = %s")
        params.append(group_id)

    if from_date:
        conditions.append("publication_date >= %s")
        params.append(from_date)

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    offset = (page - 1) * limit

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        # Get total count
        cur.execute(f"SELECT COUNT(*) as count FROM articles {where_clause}", params)
        total = cur.fetchone()["count"]

        # Get articles
        query = f"""
            SELECT id, title, url_loc, source_id, group_id, publication_date, image_loc
            FROM articles
            {where_clause}
            ORDER BY id DESC
            LIMIT %s OFFSET %s
        """
        cur.execute(query, params + [limit, offset])
        articles_data = cur.fetchall()

    articles = [
        ArticleItem(
            id=a["id"],
            title=a.get("title"),
            url_loc=a.get("url_loc"),
            source_id=a.get("source_id"),
            group_id=a.get("group_id"),
            publication_date=a.get("publication_date").isoformat() if a.get("publication_date") else None,
            image_loc=a.get("image_loc"),
        )
        for a in articles_data
    ]

    return ArticlesResponse(articles=articles, total=total, page=page, limit=limit)
