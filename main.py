import json
import os
from datetime import datetime
from fetchers.news18 import fetch_sitemap

def main():
    print("Fetching News18 sitemap...")
    articles = fetch_sitemap(limit=10)

    os.makedirs("output", exist_ok=True)
    filename = f"output/news18_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)

    print(f"Saved {len(articles)} articles → {filename}")

if __name__ == "__main__":
    main()