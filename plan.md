# News Aggregator — System Plan

## What We're Building

A scheduled scraper that fetches the latest 10 articles per source every hour, stores them in a database, and groups articles about the same event together so an editorial team can pick topics and see all coverage.

---

## Sources

| Source | Sitemap URL | Notes |
|---|---|---|
| News18 | `https://www.news18.com/commonfeeds/v1/eng/sitemap/google-news/today.xml` | Has keywords, image |
| TOI | `https://timesofindia.indiatimes.com/sitemap/today` | Has keywords, image |
| Hindustan Times | `https://www.hindustantimes.com/sitemap/news.xml` | Has keywords, image |
| NDTV | `https://www.ndtv.com/sitemap.xml?yyyy=YYYY&mm=MM&sitename=ndtv-news&category=` | Year/month dynamic from today's date |
| Indian Express | `https://indianexpress.com/news-sitemap.xml` | Has keywords, image |

Zee News blocked (Cloudflare + robots.txt explicitly disallows AI scrapers).

---

## File Structure

```
news-aggregator/
├── fetchers/
│   ├── news18.py          # NAMESPACES, HEADERS, clean() — shared by other fetchers
│   ├── toi.py
│   ├── ht.py
│   ├── ndtv.py            # dynamic sitemap URL from today's date
│   └── indianexpress.py
├── output/                # local JSON dumps (dev/debug only)
├── main.py                # runs all sources, saves JSON
└── requirements.txt
```

### requirements.txt
```
httpx
lxml
trafilatura
curl_cffi        # if httpx gets 403'd (TLS fingerprinting bypass)
```

---

## Per-Article JSON Schema (from fetcher)

```json
{
  "url_loc": "https://...",
  "lastmod": "2026-05-11T15:50:34+05:30",
  "news": {
    "name": "Hindustan Times",
    "language": "en",
    "publication_date": "2026-05-11T15:50:34+05:30",
    "title": "Article title here",
    "keywords": ["keyword1", "keyword2"]
  },
  "image_loc": "https://...",
  "meta": {
    "description": "SEO meta description",
    "og_title": "OG title"
  },
  "content": "Full article body text extracted by trafilatura"
}
```

---

## Database Schema

### `sources` (lookup table)
```sql
create table sources (
    id   smallint primary key generated always as identity,
    name text not null unique   -- 'NDTV', 'TOI', 'News18', etc.
);
```

### `article_groups` (one row per event cluster)
```sql
create table article_groups (
    id               bigint primary key generated always as identity,
    topic_label      text,           -- LLM-generated from top 3 member titles
    group_keywords   text[],         -- union of all member jaccard_keywords (for pre-filter)
    centroid         vector(N),      -- average of all member embeddings (point-by-point)
    article_count    int default 1,  -- needed for incremental centroid update (see below)
    first_seen_at    timestamptz default now(),
    last_updated_at  timestamptz default now(),
    expires_at       timestamptz     -- set to first_seen_at + 48h, bumped forward on each new article
);
```

### `articles` (one row per article)
```sql
create table articles (
    id               bigint primary key generated always as identity,
    source_id        smallint references sources(id),
    group_id         bigint references article_groups(id),  -- nullable until grouped

    -- sitemap fields
    url_loc          text not null unique,
    lastmod          timestamptz,
    publication_date timestamptz,

    -- content
    title            text,
    keywords         text[],          -- raw from sitemap
    jaccard_keywords text[],          -- normalised: lowercased, deduplicated, len > 3
                                      -- populated from keywords if present, else meta_description
    meta_description text,
    image_loc        text,
    content          text,

    -- vector
    embedding        vector(N),       -- embed(title + " " + keywords joined)

    scraped_at       timestamptz default now()
);
```

**Choose N before creating the table — cannot be altered later:**
- `384` → `sentence-transformers/all-MiniLM-L6-v2` (free, local, fast)
- `1536` → OpenAI `text-embedding-3-small` (API cost, higher quality)

---

## Indexes

```sql
-- Dedup check on insert (exact URL lookup)
create unique index on articles (url_loc);

-- Latest articles first
create index on articles (publication_date desc);

-- Fetch all articles belonging to a group
create index on articles (group_id);

-- Jaccard pre-filter: fast array overlap (&&) without full table scan
create index on articles using gin (jaccard_keywords);
create index on article_groups using gin (group_keywords);

-- Similarity search: match new article to nearest active group centroid
create index on article_groups using ivfflat (centroid vector_cosine_ops)
    with (lists = 100);

-- Editorial use only: find articles similar to a given article
create index on articles using ivfflat (embedding vector_cosine_ops)
    with (lists = 100);
```

### Why ivfflat, not hnsw?
- **ivfflat** — divides vector space into `lists` clusters, searches only nearest cluster. Slightly less accurate but fast inserts. Correct for hourly batch ingestion.
- **hnsw** — graph-based, better recall, faster queries, higher memory, slower inserts. Better if editorial search becomes the dominant workload.
- Rule of thumb: if inserting > querying → ivfflat. If querying >> inserting → hnsw.

### Index explainer
| Index | Type | Helps with |
|---|---|---|
| `articles(url_loc)` | unique btree | "Have I seen this URL?" — O(log n) instead of full scan |
| `articles(publication_date desc)` | btree | "Latest 10 articles" queries |
| `articles(group_id)` | btree | "All articles in group X" without full scan |
| `articles/groups(jaccard_keywords)` | GIN | Per-keyword inverted map → fast `&&` array overlap for Jaccard |
| `article_groups(centroid)` | ivfflat | "Which active group is nearest?" — approximate nearest neighbour |
| `articles(embedding)` | ivfflat | Editorial: "Articles similar to this one" |

---

## Grouping Logic

### Why centroid?
Instead of comparing a new article against every existing article (O(n)), we maintain one centroid vector per group and compare against that. Far cheaper, and accuracy is preserved because the centroid represents the average meaning of all members.

### Incremental centroid update (no re-fetch needed)
```
new_centroid = (old_centroid × n + new_embedding) / (n + 1)
```
`article_count` (n) is stored on the group row for exactly this calculation.

### jaccard_keywords population
```python
source = keywords if keywords else meta_description  # fallback if keywords empty
jaccard_keywords = list(set(
    w.lower() for w in source.replace(",", " ").split()
    if len(w) > 3
))
```

### Similarity thresholds
- Jaccard keyword overlap: `|A ∩ B| / |A ∪ B| > 0.3` (pre-filter, cheap)
- Cosine distance on centroid: `centroid <=> embedding < 0.18` (= similarity > 0.82)
- Both must pass to assign to an existing group.

### Group expiry + bumping
- Groups created with `expires_at = now() + interval '48 hours'`
- On every new article added to a group: `expires_at = now() + interval '48 hours'`
- Active stories stay alive; dead topics expire naturally
- Similarity search always filters `WHERE expires_at > now()`

---

## Pipeline — Order of Operations (per article, per run)

```
1. FETCH
   fetch sitemap → parse XML → extract top 10 URLs

2. DEDUPLICATE
   SELECT 1 FROM articles WHERE url_loc = $url
   → skip if exists

3. BUILD jaccard_keywords
   source = keywords if non-empty else meta_description
   normalise → lowercase, split, deduplicate, filter len > 3

4. EMBED
   input = title + " " + ", ".join(keywords or [meta_description])
   embedding = embed(input)   # vector(N)

5. JACCARD PRE-FILTER
   SELECT id, group_keywords FROM article_groups
   WHERE expires_at > now()
   → compute jaccard(article.jaccard_keywords, group.group_keywords)
   → keep candidates where jaccard > 0.3

6. VECTOR CHECK (on jaccard survivors only)
   SELECT id, centroid FROM article_groups
   WHERE id IN (jaccard_candidates)
   ORDER BY centroid <=> $embedding
   LIMIT 1
   → accept if distance < 0.18

7a. MATCH FOUND → assign group
    UPDATE article_groups SET
        centroid       = (centroid * article_count + $embedding) / (article_count + 1),
        article_count  = article_count + 1,
        group_keywords = array_distinct(group_keywords || $jaccard_keywords),
        last_updated_at = now(),
        expires_at     = now() + interval '48 hours'
    WHERE id = $group_id

7b. NO MATCH → create new group
    INSERT INTO article_groups
        (centroid, group_keywords, article_count, expires_at)
    VALUES ($embedding, $jaccard_keywords, 1, now() + interval '48 hours')
    → returns new group_id

8. INSERT ARTICLE
   INSERT INTO articles (..., group_id, embedding, jaccard_keywords)

9. GENERATE topic_label (async, after insert)
   If group is new OR label is null:
   fetch top 3 titles from group → call LLM → store topic_label
```

---

## Scheduling

- Run every hour via `APScheduler` (Python) or OS cron
- Each run is stateless — full pipeline from fetch to insert
- Duplicates handled by `url_loc` unique constraint (safe to re-run)

---

## Next Steps (in order)

1. Set up Supabase project + enable pgvector + run schema SQL
2. Write `db.py` — connection + insert + group-matching functions
3. Choose embedding model + write `embed.py`
4. Wire pipeline: fetcher output → embed → group match → insert
5. Add `APScheduler` wrapper in `main.py`
6. Add LLM topic label generation (async, low priority)
7. Build editorial UI (read-only queries on `article_groups` + members)
