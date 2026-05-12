import json
import os
from datetime import datetime
from fetchers import news18, toi, zeenews, ht, indianexpress, ndtv

SOURCES = {
    "news18": news18,
    "toi":    toi,
    "ht":     ht,
    "indianexpress": indianexpress,
    # "zeenews": zeenews, #403
    # "ndtv": ndtv #403
}

def main():
    os.makedirs("output", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    for name, fetcher in SOURCES.items():
        print(f"Fetching {name}...")
        articles = fetcher.fetch_sitemap(limit=10)
        filename = f"output/{name}_{timestamp}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(articles, f, ensure_ascii=False, indent=2)
        print(f"  Saved {len(articles)} articles → {filename}")

if __name__ == "__main__":
    main()