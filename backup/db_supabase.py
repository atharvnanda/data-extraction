import os
import re
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

SOURCE_IDS = {
    "news18":        1,
    "toi":           2,
    "ht":            3,
    "indianexpress": 4,
    "zeenews":       6,
    "ndtv":          7,
}

JACCARD_THRESHOLD = 0.1
COSINE_THRESHOLD  = 0.33   # cosine distance (similarity >= 0.67)


def get_client():
    """Create a Supabase client (HTTPS on port 443 — works on corporate networks)."""
    return create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_KEY"],
    )


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

def url_exists(sb, url: str) -> bool:
    result = sb.table("articles").select("url_loc").eq("url_loc", url).limit(1).execute()
    return len(result.data) > 0


# ── Group matching ────────────────────────────────────────────────────────────

def find_matching_group(sb, jaccard_kws: list[str], embedding: list[float]) -> tuple[int | None, dict]:
    """
    1. Pull all active groups.
    2. Jaccard pre-filter.
    3. Vector similarity on survivors (via RPC).
    Returns (group_id, debug_data).
    """
    debug_data = {
        "jaccard_phase": {"threshold": JACCARD_THRESHOLD, "top_matches": [], "candidate_ids": []},
        "vector_phase": {"performed": False, "threshold": COSINE_THRESHOLD, "best_match": None}
    }

    # Fetch active groups via PostgREST
    result = sb.table("article_groups") \
        .select("id, group_keywords") \
        .gt("expires_at", "now()") \
        .execute()
    active_groups = result.data

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

    # Vector check via RPC (anchor embedding, immutable, no drift)
    debug_data["vector_phase"]["performed"] = True
    result = sb.rpc("match_group", {
        "query_embedding": embedding,
        "candidate_ids": debug_data["jaccard_phase"]["candidate_ids"]
    }).execute()

    if not result.data:
        return None, debug_data

    row = result.data[0]
    group_id = row["group_id"]
    dist = row["dist"]

    debug_data["vector_phase"]["best_match"] = {
        "group_id": group_id,
        "distance": round(float(dist), 4)
    }

    if dist < COSINE_THRESHOLD:
        return group_id, debug_data
    
    return None, debug_data


def update_group(sb, group_id: int, jaccard_kws: list[str]):
    """Update group metadata via RPC. Anchor embedding is never modified."""
    sb.rpc("update_group_metadata", {
        "target_group_id": group_id,
        "new_keywords": jaccard_kws
    }).execute()


def create_group(sb, embedding: list[float], jaccard_kws: list[str]) -> int:
    """Create a new group via RPC. The first article's embedding becomes the immutable anchor."""
    result = sb.rpc("create_group_with_anchor", {
        "p_embedding": embedding,
        "p_keywords": jaccard_kws
    }).execute()
    return result.data


# ── Insert article ────────────────────────────────────────────────────────────

def insert_article(sb, article: dict, source_key: str,
                   embedding: list[float], jaccard_kws: list[str], group_id: int):
    news = article.get("news", {}) or {}
    meta = article.get("meta", {}) or {}

    # Convert empty strings to None for timestamps
    nullif = lambda v: v if v else None

    sb.rpc("insert_article_with_embedding", {
        "p_source_id": SOURCE_IDS[source_key],
        "p_group_id": group_id,
        "p_url_loc": article.get("url_loc"),
        "p_lastmod": nullif(article.get("lastmod")),
        "p_publication_date": nullif(news.get("publication_date")),
        "p_title": news.get("title"),
        "p_keywords": news.get("keywords") or [],
        "p_jaccard_keywords": jaccard_kws,
        "p_meta_keywords": meta.get("keywords") or "",
        "p_image_loc": article.get("image_loc"),
        "p_content": article.get("content"),
        "p_embedding": embedding,
    }).execute()
