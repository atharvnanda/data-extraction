import os
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

SOURCE_IDS = {
    "news18":        1,
    "toi":           2,
    "ht":            3,
    "indianexpress": 4,
}

JACCARD_THRESHOLD = 0.3
COSINE_THRESHOLD  = 0.18   # distance, not similarity (1 - 0.82)


def get_conn():
    return psycopg2.connect(os.environ["SUPABASE_DB_URL"])


# ── Jaccard ──────────────────────────────────────────────────────────────────

def jaccard(a: list[str], b: list[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def build_jaccard_keywords(article: dict) -> list[str]:
    keywords = article.get("news", {}).get("keywords", []) or []
    if not keywords:
        desc = (article.get("meta", {}) or {}).get("description", "") or ""
        keywords = desc.replace(",", " ").split()
    return list(set(
        w.lower() for w in keywords if len(w) > 3
    ))


# ── Dedup ─────────────────────────────────────────────────────────────────────

def url_exists(conn, url: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("select 1 from articles where url_loc = %s", (url,))
        return cur.fetchone() is not None


# ── Group matching ────────────────────────────────────────────────────────────

def find_matching_group(conn, jaccard_kws: list[str], embedding: list[float]) -> int | None:
    """
    1. Pull all active groups with their group_keywords.
    2. Jaccard pre-filter (Python side — groups are few).
    3. Vector similarity on survivors (DB side).
    Returns group_id or None.
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            select id, group_keywords
            from article_groups
            where expires_at > now()
        """)
        active_groups = cur.fetchall()

    candidates = [
        g["id"] for g in active_groups
        if jaccard(jaccard_kws, g["group_keywords"] or []) >= JACCARD_THRESHOLD
    ]

    if not candidates:
        return None

    with conn.cursor() as cur:
        cur.execute("""
            select id
            from article_groups
            where id = any(%s)
            order by centroid <=> %s::vector
            limit 1
        """, (candidates, embedding))
        row = cur.fetchone()

    if not row:
        return None

    # verify cosine distance is within threshold
    with conn.cursor() as cur:
        cur.execute("""
            select centroid <=> %s::vector as dist
            from article_groups
            where id = %s
        """, (embedding, row[0]))
        dist = cur.fetchone()[0]

    return row[0] if dist < COSINE_THRESHOLD else None


def update_group(conn, group_id: int, embedding: list[float], jaccard_kws: list[str]):
    with conn.cursor() as cur:
        cur.execute("""
            update article_groups set
                centroid        = ((centroid * article_count) + %s::vector) / (article_count + 1),
                article_count   = article_count + 1,
                group_keywords  = (
                    select array_agg(distinct kw)
                    from unnest(group_keywords || %s::text[]) as kw
                ),
                last_updated_at = now(),
                expires_at      = now() + interval '48 hours'
            where id = %s
        """, (embedding, jaccard_kws, group_id))
    conn.commit()


def create_group(conn, embedding: list[float], jaccard_kws: list[str]) -> int:
    with conn.cursor() as cur:
        cur.execute("""
            insert into article_groups
                (centroid, group_keywords, article_count, expires_at)
            values
                (%s::vector, %s, 1, now() + interval '48 hours')
            returning id
        """, (embedding, jaccard_kws))
        group_id = cur.fetchone()[0]
    conn.commit()
    return group_id


# ── Insert article ────────────────────────────────────────────────────────────

def insert_article(conn, article: dict, source_key: str,
                   embedding: list[float], jaccard_kws: list[str], group_id: int):
    news = article.get("news", {}) or {}
    meta = article.get("meta", {}) or {}

    with conn.cursor() as cur:
        cur.execute("""
            insert into articles (
                source_id, group_id, url_loc, lastmod, publication_date,
                title, keywords, jaccard_keywords, meta_description,
                image_loc, content, embedding
            ) values (
                %s, %s, %s, %s::timestamptz, %s::timestamptz,
                %s, %s, %s, %s,
                %s, %s, %s::vector
            )
            on conflict (url_loc) do nothing
        """, (
            SOURCE_IDS[source_key],
            group_id,
            article.get("url_loc"),
            article.get("lastmod"),
            news.get("publication_date"),
            news.get("title"),
            news.get("keywords") or [],
            jaccard_kws,
            meta.get("description") or "",
            article.get("image_loc"),
            article.get("content"),
            embedding,
        ))
    conn.commit()