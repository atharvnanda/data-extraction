import httpx
from lxml import etree
import trafilatura
import json
from datetime import datetime
import re

SITEMAP_URL = "https://timesofindia.indiatimes.com/staticsitemap/toi/news/sitemap-today-1.xml" #"https://timesofindia.indiatimes.com/sitemap/today"

NAMESPACES = {
    "sm":    "http://www.sitemaps.org/schemas/sitemap/0.9",
    "news":  "http://www.google.com/schemas/sitemap-news/0.9",
    "image": "http://www.google.com/schemas/sitemap-image/1.1",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


def clean(text: str | None) -> str:
    """Strip whitespace / CDATA artifacts."""
    if text is None:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def fetch_sitemap(limit: int = 10) -> list[dict]:
    with httpx.Client(headers=HEADERS, timeout=30, follow_redirects=True) as client:
        resp = client.get(SITEMAP_URL)
        resp.raise_for_status()

    xml_text = re.sub(r"<script[^>]*/?>", "", resp.text)
    root = etree.fromstring(xml_text.encode())

    urls = root.findall("sm:url", NAMESPACES)[:limit]
    articles = []

    with httpx.Client(headers=HEADERS, timeout=30, follow_redirects=True) as client:
        for url_el in urls:
            entry = parse_url_element(url_el, client)
            if entry:
                articles.append(entry)

    return articles


def parse_url_element(url_el, client: httpx.Client) -> dict | None:
    loc = clean(url_el.findtext("sm:loc", namespaces=NAMESPACES))
    lastmod = clean(url_el.findtext("sm:lastmod", namespaces=NAMESPACES))

    news_el = url_el.find("news:news", NAMESPACES)
    pub_el  = news_el.find("news:publication", NAMESPACES) if news_el is not None else None

    name     = clean(pub_el.findtext("news:name",     namespaces=NAMESPACES)) if pub_el  else ""
    language = clean(pub_el.findtext("news:language", namespaces=NAMESPACES)) if pub_el  else ""
    pub_date = clean(news_el.findtext("news:publication_date", namespaces=NAMESPACES)) if news_el else ""
    title    = clean(news_el.findtext("news:title",   namespaces=NAMESPACES)) if news_el else ""
    keywords = clean(news_el.findtext("news:keywords",namespaces=NAMESPACES)) if news_el else ""

    image_el  = url_el.find("image:image", NAMESPACES)
    image_loc = clean(image_el.findtext("image:loc", namespaces=NAMESPACES)) if image_el is not None else ""

    def fetch_meta_keywords(html: str) -> str:
        try:
            tree = etree.fromstring(html.encode(), etree.HTMLParser())
            el = tree.find('.//meta[@name="keywords"]')
            return el.get("content", "").strip() if el is not None else ""
        except Exception:
            return ""

    # Scrape article body
    content = ""
    meta_keywords = ""
    if loc:
        try:
            resp = client.get(loc)
            content = trafilatura.extract(resp.text) or ""
            meta_keywords = fetch_meta_keywords(resp.text)
        except Exception as e:
            content = f"[fetch error: {e}]"

    return {
        "url_loc":  loc,
        "lastmod":  lastmod,
        "news": {
            "name":             name,
            "language":         language,
            "publication_date": pub_date,
            "title":            title,
            "keywords":         [k.strip() for k in keywords.split(",") if k.strip()],
        },
        "image_loc": image_loc,
        "meta": {
            "keywords": meta_keywords,
        },
        "content":   content,
    }