import httpx
from lxml import etree
import trafilatura
import re
from fetchers.news18 import HEADERS, clean

SITEMAP_URL = "https://indianexpress.com/sitemap/today.xml"  # https://indianexpress.com/news-sitemap.xml

# IE uses different namespace alias for news
NAMESPACES = {
    "sm":    "http://www.sitemaps.org/schemas/sitemap/0.9",
    "n":     "http://www.google.com/schemas/sitemap-news/0.9",
    "image": "http://www.google.com/schemas/sitemap-image/1.1",
}


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


def fetch_meta(html: str) -> dict:
    """Extract SEO meta tags from article HTML."""
    try:
        tree = etree.fromstring(html.encode(), etree.HTMLParser())
        def meta(name_attr, name_val):
            el = tree.find(f'.//meta[@{name_attr}="{name_val}"]')
            return clean(el.get("content", "")) if el is not None else ""

        return {
            "keywords":    meta("name", "keywords"),
            "description": meta("name", "description"),
            "og_title":    meta("property", "og:title"),
        }
    except Exception:
        return {"keywords": "", "description": "", "og_title": ""}


def parse_url_element(url_el, client: httpx.Client) -> dict | None:
    loc     = clean(url_el.findtext("sm:loc",     namespaces=NAMESPACES))
    lastmod = clean(url_el.findtext("sm:lastmod", namespaces=NAMESPACES))

    html    = ""
    content = ""
    meta    = {}

    if loc:
        try:
            resp    = client.get(loc)
            html    = resp.text
            content = trafilatura.extract(html) or ""
            meta    = fetch_meta(html)
        except Exception as e:
            content = f"[fetch error: {e}]"

    return {
        "url_loc": loc,
        "lastmod": lastmod,
        "meta": {
            "keywords":    [k.strip() for k in meta.get("keywords", "").split(",") if k.strip()],
            "description": meta.get("description", ""),
            "og_title":    meta.get("og_title", ""),
        },
        "content": content,
    }