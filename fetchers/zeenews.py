import httpx
from lxml import etree
import trafilatura
import re

SITEMAP_URL = "https://zeenews.india.com/sitemap.xml"

NAMESPACES = {
    "sm":    "http://www.sitemaps.org/schemas/sitemap/0.9",
    "news":  "http://www.google.com/schemas/sitemap-news/0.9",
    "image": "http://www.google.com/schemas/sitemap-image/1.1",
}

HEADERS = {
    "User-Agent": "Chrome/124.0.0.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.google.com/", # Makes it look like you came from a search engine
    "Connection": "keep-alive",
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
    loc     = clean(url_el.findtext("sm:loc", namespaces=NAMESPACES))
    # Zee News has no <lastmod>

    news_el = url_el.find("news:news", NAMESPACES)
    pub_el  = news_el.find("news:publication", NAMESPACES) if news_el is not None else None

    name     = clean(pub_el.findtext("news:name",     namespaces=NAMESPACES)) if pub_el  else ""
    language = clean(pub_el.findtext("news:language", namespaces=NAMESPACES)) if pub_el  else ""
    pub_date = clean(news_el.findtext("news:publication_date", namespaces=NAMESPACES)) if news_el else ""
    title    = clean(news_el.findtext("news:title",    namespaces=NAMESPACES)) if news_el else ""
    keywords_raw = clean(news_el.findtext("news:keywords", namespaces=NAMESPACES)) if news_el else ""

    # Zee injects garbage encoding artifacts (e.g. "Â") — strip them
    keywords_clean = re.sub(r"[^\x00-\x7F]+", "", keywords_raw)

    # add this function to each fetcher file
    def fetch_meta_description(html: str) -> str:
        try:
            tree = etree.fromstring(html.encode(), etree.HTMLParser())
            el = tree.find('.//meta[@name="description"]')
            return el.get("content", "").strip() if el is not None else ""
        except Exception:
            return ""

    content = ""
    meta_description = ""
    if loc:
        try:
            resp    = client.get(loc)
            content = trafilatura.extract(resp.text) or ""
            meta_description = fetch_meta_description(resp.text)
        except Exception as e:
            content = f"[fetch error: {e}]"

    return {
        "url_loc": loc,
        "lastmod": None,          # not present in Zee News sitemap
        "news": {
            "name":             name,
            "language":         language,
            "publication_date": pub_date,
            "title":            title,
            "keywords":         [k.strip() for k in keywords_clean.split(",") if k.strip()],
        },
        "image_loc": None,        # not present in Zee News sitemap
        "meta": {
            "description": meta_description,
        },
        "content":   content,
    }