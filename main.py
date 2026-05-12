import json
import os
from datetime import datetime
from fetchers import news18, toi, zeenews, ht, indianexpress, ndtv
from pipeline.embed import embed_text, build_embed_input
from pipeline.db import (
    get_conn, url_exists, build_jaccard_keywords,
    find_matching_group, update_group, create_group, insert_article
)

SOURCES = {
    "news18": news18,
    "toi":    toi,
    # "ht":     ht,
    # "indianexpress": indianexpress,
    # "zeenews": zeenews, #403
    # "ndtv": ndtv #403
}

def process_article(conn, article: dict, source_key: str):
    url = article.get("url_loc")
    if not url:
        return

    if url_exists(conn, url):
        print(f"    skip (exists): {url}")
        return

    embedding   = embed_text(build_embed_input(article))
    jaccard_kws = build_jaccard_keywords(article)

    group_id = find_matching_group(conn, jaccard_kws, embedding)
    if group_id:
        update_group(conn, group_id, embedding, jaccard_kws)
        print(f"    grouped → {group_id}: {article.get('news', {}).get('title', '')[:60]}")
    else:
        group_id = create_group(conn, embedding, jaccard_kws)
        print(f"    new group {group_id}: {article.get('news', {}).get('title', '')[:60]}")

    insert_article(conn, article, source_key, embedding, jaccard_kws, group_id)


def main():
    conn = get_conn()
    try:
        for source_key, fetcher in SOURCES.items():
            print(f"\nFetching {source_key}...")
            try:
                articles = fetcher.fetch_sitemap(limit=10)
                print(f"  fetched {len(articles)} articles")
            except Exception as e:
                print(f"  fetch error: {e}")
                continue

            for article in articles:
                try:
                    process_article(conn, article, source_key)
                except Exception as e:
                    print(f"  pipeline error: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()