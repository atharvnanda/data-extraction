-- ============================================================================
-- Supabase RPC Functions
-- Run these in the Supabase SQL Editor (Dashboard → SQL Editor → New Query)
-- These enable pgvector and complex SQL operations over the REST API (port 443)
-- ============================================================================


-- 1. match_group: Find the nearest group by anchor embedding cosine distance
--    Called by: find_matching_group() in db.py
CREATE OR REPLACE FUNCTION match_group(
    query_embedding vector(512),
    candidate_ids bigint[]
)
RETURNS TABLE(group_id bigint, dist float)
LANGUAGE sql
AS $$
    SELECT id AS group_id, (anchor_embedding <=> query_embedding)::float AS dist
    FROM article_groups
    WHERE id = ANY(candidate_ids)
    ORDER BY dist
    LIMIT 1;
$$;


-- 2. update_group_metadata: Update group keywords, count, and timestamps
--    Called by: update_group() in db.py
--    Handles the array_agg(distinct ...) which PostgREST can't do
CREATE OR REPLACE FUNCTION update_group_metadata(
    target_group_id bigint,
    new_keywords text[]
)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE article_groups SET
        article_count   = article_count + 1,
        group_keywords  = (
            SELECT array_agg(DISTINCT kw)
            FROM unnest(group_keywords || new_keywords) AS kw
        ),
        last_updated_at = now(),
        expires_at      = now() + interval '48 hours'
    WHERE id = target_group_id;
END;
$$;


-- 3. insert_article_with_embedding: Insert an article with vector casting
--    Called by: insert_article() in db.py
--    Handles the vector cast and ON CONFLICT which PostgREST can't do cleanly
CREATE OR REPLACE FUNCTION insert_article_with_embedding(
    p_source_id smallint,
    p_group_id bigint,
    p_url_loc text,
    p_lastmod timestamptz,
    p_publication_date timestamptz,
    p_title text,
    p_keywords text[],
    p_jaccard_keywords text[],
    p_meta_keywords text,
    p_image_loc text,
    p_content text,
    p_embedding vector(512)
)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO articles (
        source_id, group_id, url_loc, lastmod, publication_date,
        title, keywords, jaccard_keywords, meta_keywords,
        image_loc, content, embedding
    ) VALUES (
        p_source_id, p_group_id, p_url_loc, p_lastmod, p_publication_date,
        p_title, p_keywords, p_jaccard_keywords, p_meta_keywords,
        p_image_loc, p_content, p_embedding
    )
    ON CONFLICT (url_loc) DO NOTHING;
END;
$$;


-- 4. create_group_with_anchor: Create a new group and return its ID
--    Called by: create_group() in db.py
CREATE OR REPLACE FUNCTION create_group_with_anchor(
    p_embedding vector(512),
    p_keywords text[]
)
RETURNS bigint
LANGUAGE plpgsql
AS $$
DECLARE
    new_id bigint;
BEGIN
    INSERT INTO article_groups
        (anchor_embedding, group_keywords, article_count, expires_at)
    VALUES
        (p_embedding, p_keywords, 1, now() + interval '48 hours')
    RETURNING id INTO new_id;

    RETURN new_id;
END;
$$;
