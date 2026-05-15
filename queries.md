# Raw SQL Queries Reference (psycopg2 version)

Reference file for all raw SQL queries used in the pipeline.
Preserved for future migration back from supabase-py if needed.

---

## Connection

```python
psycopg2.connect(
    host=os.environ["SUPABASE_HOST"],
    port=os.environ["SUPABASE_PORT"],
    dbname=os.environ["SUPABASE_DB"],
    user=os.environ["SUPABASE_USER"],
    password=os.environ["SUPABASE_PASSWORD"],
    sslmode="require"
)
```

---

## url_exists

```sql
SELECT 1 FROM articles WHERE url_loc = %s
```

---

## get_active_groups (used in find_matching_group)

```sql
SELECT id, group_keywords
FROM article_groups
WHERE expires_at > now()
```

---

## match_group — vector similarity search (used in find_matching_group)

```sql
SELECT id, anchor_embedding <=> %s::vector AS dist
FROM article_groups
WHERE id = ANY(%s)
ORDER BY dist
LIMIT 1
```

---

## update_group

```sql
UPDATE article_groups SET
    article_count   = article_count + 1,
    group_keywords  = (
        SELECT array_agg(distinct kw)
        FROM unnest(group_keywords || %s::text[]) AS kw
    ),
    last_updated_at = now(),
    expires_at      = now() + interval '48 hours'
WHERE id = %s
```

---

## create_group

```sql
INSERT INTO article_groups
    (anchor_embedding, group_keywords, article_count, expires_at)
VALUES
    (%s::vector, %s, 1, now() + interval '48 hours')
RETURNING id
```

---

## insert_article

```sql
INSERT INTO articles (
    source_id, group_id, url_loc, lastmod, publication_date,
    title, keywords, jaccard_keywords, meta_keywords,
    image_loc, content, embedding
) VALUES (
    %s, %s, %s, %s::timestamptz, %s::timestamptz,
    %s, %s, %s, %s,
    %s, %s, %s::vector
)
ON CONFLICT (url_loc) DO NOTHING
```
