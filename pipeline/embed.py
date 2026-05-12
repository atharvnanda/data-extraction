import cohere
import os
from dotenv import load_dotenv

load_dotenv()
_client = cohere.ClientV2(os.environ["COHERE_API_KEY"])

def embed_text(text: str) -> list[float]:
    resp = _client.embed(
        texts=[text],
        model="embed-english-v4.0",
        input_type="search_document",
        embedding_types=["float"],
        output_dimension=512,
    )
    return resp.embeddings.float[0]

# embed.py
def build_embed_input(article: dict) -> str:
    title    = article.get("news", {}).get("title", "") or ""
    keywords = article.get("news", {}).get("keywords") or []
    if not keywords:
        desc = article.get("meta", {}).get("description", "") or ""
        keywords = desc.replace(",", " ").split()
    kw_str = ", ".join(keywords)
    return f"{title} {kw_str}".strip()