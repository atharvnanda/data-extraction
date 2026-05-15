import json
import os
from datetime import datetime
from fetchers import news18, toi, zeenews, ht, indianexpress, ndtv
from pipeline.embed import embed_text, build_embed_input
from pipeline.db import (
    get_client, url_exists, build_jaccard_keywords,
    find_matching_group, update_group, create_group, insert_article
)

SOURCES = {
    "news18": news18,
    "toi":    toi,
    "ht":     ht,
    "indianexpress": indianexpress,
    "zeenews": zeenews, 
    "ndtv": ndtv 
}

def process_article(sb, article: dict, source_key: str, run_report: list):
    url = article.get("url_loc")
    if not url:
        return

    if url_exists(sb, url):
        print(f"    skip (exists): {url}")
        return

    embedding   = embed_text(build_embed_input(article))
    jaccard_kws = build_jaccard_keywords(article)

    group_id, debug_data = find_matching_group(sb, jaccard_kws, embedding)
    
    action = "new_group"
    if group_id:
        update_group(sb, group_id, jaccard_kws)
        print(f"    grouped -> {group_id}: {article.get('news', {}).get('title', '')[:60]}")
        action = "grouped"
    else:
        group_id = create_group(sb, embedding, jaccard_kws)
        print(f"    new group {group_id}: {article.get('news', {}).get('title', '')[:60]}")

    insert_article(sb, article, source_key, embedding, jaccard_kws, group_id)

    # Add to run report
    run_report.append({
        "article": {
            "title": article.get("news", {}).get("title"),
            "url": url,
            "source": source_key,
            "extracted_keywords": jaccard_kws
        },
        "scoring": debug_data,
        "final_action": action,
        "assigned_id": group_id
    })


def main():
    sb = get_client()
    run_report = []
    
    # Setup log file path
    os.makedirs("logs", exist_ok=True)
    log_filename = datetime.now().strftime("%Y%m%d_%H%M%S.json")
    log_path = os.path.join("logs", log_filename)

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
                process_article(sb, article, source_key, run_report)
            except Exception as e:
                print(f"  pipeline error: {e}")
    
    # Save logs
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(run_report, f, indent=2, ensure_ascii=False)
    print(f"\nRun report saved to: {log_path}")


if __name__ == "__main__":
    main()