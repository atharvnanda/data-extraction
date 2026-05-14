from curl_cffi import requests as cffi_requests
from lxml import etree
import trafilatura
import re
from datetime import datetime
from fetchers.news18 import clean

NAMESPACES = {
    "sm":    "http://www.sitemaps.org/schemas/sitemap/0.9",
    "news":  "http://www.google.com/schemas/sitemap-news/0.9",
    "image": "http://www.google.com/schemas/sitemap-image/1.1",
}

def get_sitemap_url() -> str:
    now = datetime.now()
    return (
        f"https://www.ndtv.com/sitemap.xml"
        f"?yyyy={now.year}&mm={now.month}&sitename=ndtv-news&category="
    )

def fetch_meta(html: str) -> dict:
    try:
        tree = etree.fromstring(html.encode(), etree.HTMLParser())
        def meta(attr, val):
            el = tree.find(f'.//meta[@{attr}="{val}"]')
            return el.get("content", "").strip() if el is not None else ""
        return {
            "description": meta("name", "description"),
            "keywords":    meta("name", "keywords"),
            "og_title":    meta("property", "og:title"),
        }
    except Exception:
        return {"description": "", "keywords": "", "og_title": ""}

def fetch_sitemap(limit: int = 10) -> list[dict]:
    url = get_sitemap_url()
    with cffi_requests.Session(impersonate="chrome120") as session:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()

        xml_text = re.sub(r"<script[^>]*/?>", "", resp.text)
        root = etree.fromstring(xml_text.encode())
        urls = root.findall("sm:url", NAMESPACES)[:limit]
        articles = []

        for url_el in urls:
            entry = parse_url_element(url_el, session)
            if entry:
                articles.append(entry)

    return articles

def parse_url_element(url_el, session: cffi_requests.Session) -> dict | None:
    loc     = clean(url_el.findtext("sm:loc",     namespaces=NAMESPACES))
    lastmod = clean(url_el.findtext("sm:lastmod", namespaces=NAMESPACES))

    news_el = url_el.find("news:news", NAMESPACES)
    pub_el  = news_el.find("news:publication", NAMESPACES) if news_el is not None else None

    name     = clean(pub_el.findtext("news:name",     namespaces=NAMESPACES)) if pub_el  else ""
    language = clean(pub_el.findtext("news:language", namespaces=NAMESPACES)) if pub_el  else ""
    pub_date = clean(news_el.findtext("news:publication_date", namespaces=NAMESPACES)) if news_el else ""
    title    = clean(news_el.findtext("news:title",    namespaces=NAMESPACES)) if news_el else ""
    keywords = clean(news_el.findtext("news:keywords", namespaces=NAMESPACES)) if news_el else ""

    image_el  = url_el.find("image:image", NAMESPACES)
    image_loc = clean(image_el.findtext("image:loc", namespaces=NAMESPACES)) if image_el is not None else ""

    content, meta = "", {}
    if loc:
        try:
            resp    = session.get(loc, timeout=30)
            html    = resp.text
            content = trafilatura.extract(html) or ""
            meta    = fetch_meta(html)
        except Exception as e:
            content = f"[fetch error: {e}]"

    # Fallback: use og:title if sitemap title is missing
    if not title:
        title = meta.get("og_title", "")

    return {
        "url_loc": loc,
        "lastmod": lastmod,
        "news": {
            "name":             name,
            "language":         language,
            "publication_date": pub_date,
            "title":            title,
            "keywords":         [k.strip() for k in keywords.split(",") if k.strip()],
        },
        "image_loc": image_loc,
        "meta": {
            "description": meta.get("description", ""),
            "keywords":    meta.get("keywords", ""),
            "og_title":    meta.get("og_title", ""),
        },
        "content": content,
    }