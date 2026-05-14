import os
import re
import psycopg2
import psycopg2.extras
import json
from dotenv import load_dotenv

load_dotenv()

SOURCE_IDS = {
    "news18":        1,
    "toi":           2,
    "ht":            3,
    "indianexpress": 4,
}

JACCARD_THRESHOLD = 0.1
COSINE_THRESHOLD  = 0.3   # distance for single-article groups (sim >= 0.7)
COSINE_THRESHOLD_GROUPED = 0.4   # relaxed for multi-article groups (sim >= 0.6)


def get_conn():
    return psycopg2.connect(
        host=os.environ["SUPABASE_HOST"],
        port=os.environ["SUPABASE_PORT"],
        dbname=os.environ["SUPABASE_DB"],
        user=os.environ["SUPABASE_USER"],
        password=os.environ["SUPABASE_PASSWORD"],
        sslmode="require"
    )
    print("Connected to Supabase!")


# ── Jaccard ──────────────────────────────────────────────────────────────────

def jaccard(a: list[str], b: list[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def build_jaccard_keywords(article: dict) -> list[str]:
    # 1. Gather raw keywords from news source and meta
    news_kws = article.get("news", {}).get("keywords") or []
    meta_kws_str = (article.get("meta") or {}).get("keywords") or ""
    meta_kws = [k.strip() for k in meta_kws_str.replace(",", " ").split() if k.strip()]
    
    # 2. Include Title words (Crucial for news matching)
    title = (article.get("news") or {}).get("title") or ""
    title_words = re.split(r"[\W_]+", title)
    
    combined = news_kws + meta_kws + title_words
    
    # 3. Flatten phrases into words and normalize
    final_words = []
    for item in combined:
        # Split on spaces, dashes, underscores
        parts = re.split(r"[\s\-_,]+", item)
        final_words.extend(parts)
        
    return list(set(
        w.lower() for w in final_words 
        if len(w) > 3
    ))


# ── Dedup ─────────────────────────────────────────────────────────────────────

def url_exists(conn, url: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("select 1 from articles where url_loc = %s", (url,))
        return cur.fetchone() is not None


# ── Group matching ────────────────────────────────────────────────────────────

def find_matching_group(conn, jaccard_kws: list[str], embedding: list[float]) -> tuple[int | None, dict]:
    """
    1. Pull all active groups.
    2. Jaccard pre-filter.
    3. Vector similarity on survivors.
    Returns (group_id, debug_data).
    """
    debug_data = {
        "jaccard_phase": {"threshold": JACCARD_THRESHOLD, "top_matches": [], "candidate_ids": []},
        "vector_phase": {"performed": False, "threshold_single": COSINE_THRESHOLD, "threshold_grouped": COSINE_THRESHOLD_GROUPED, "best_match": None}
    }

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            select id, group_keywords, article_count
            from article_groups
            where expires_at > now()
        """)
        active_groups = cur.fetchall()

    # Build a lookup for article_count per group
    group_counts = {g["id"]: g["article_count"] for g in active_groups}

    scores = []
    for g in active_groups:
        score = jaccard(jaccard_kws, g["group_keywords"] or [])
        if score > 0:
            scores.append({"group_id": g["id"], "score": round(score, 4)})
        if score >= JACCARD_THRESHOLD:
            debug_data["jaccard_phase"]["candidate_ids"].append(g["id"])

    # Keep top 5 jaccard matches for logs
    debug_data["jaccard_phase"]["top_matches"] = sorted(scores, key=lambda x: x["score"], reverse=True)[:5]

    if not debug_data["jaccard_phase"]["candidate_ids"]:
        return None, debug_data

    debug_data["vector_phase"]["performed"] = True
    with conn.cursor() as cur:
        cur.execute("""
            select id, centroid <=> %s::vector as dist
            from article_groups
            where id = any(%s)
            order by dist
            limit 1
        """, (embedding, debug_data["jaccard_phase"]["candidate_ids"]))
        row = cur.fetchone()

    if not row:
        return None, debug_data

    group_id, dist = row
    count = group_counts.get(group_id, 1)
    effective_threshold = COSINE_THRESHOLD_GROUPED if count > 1 else COSINE_THRESHOLD

    debug_data["vector_phase"]["best_match"] = {
        "group_id": group_id,
        "distance": round(float(dist), 4),
        "group_article_count": count,
        "effective_threshold": effective_threshold
    }

    if dist < effective_threshold:
        return group_id, debug_data
    
    return None, debug_data


def update_group(conn, group_id: int, embedding: list[float], jaccard_kws: list[str]):
    with conn.cursor() as cur:
        cur.execute("select centroid, article_count from article_groups where id = %s", (group_id,))
        row = cur.fetchone()
        old_centroid = row[0]  # comes back as list
        if isinstance(old_centroid, str):
            old_centroid = json.loads(old_centroid)
        n = row[1]

    new_centroid = [(old_centroid[i] * n + embedding[i]) / (n + 1) for i in range(len(embedding))]

    with conn.cursor() as cur:
        cur.execute("""
            update article_groups set
                centroid        = %s::vector,
                article_count   = article_count + 1,
                group_keywords  = (
                    select array_agg(distinct kw)
                    from unnest(group_keywords || %s::text[]) as kw
                ),
                last_updated_at = now(),
                expires_at      = now() + interval '48 hours'
            where id = %s
        """, (new_centroid, jaccard_kws, group_id))
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
                title, keywords, jaccard_keywords, meta_keywords,
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
            meta.get("keywords") or "",
            article.get("image_loc"),
            article.get("content"),
            embedding,
        ))
    conn.commit()