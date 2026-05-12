
import re

def jaccard(a: list[str], b: list[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)

def build_jaccard_keywords_improved(title: str, keywords: list[str]) -> list[str]:
    all_words = []
    # Add title words
    title_words = re.sub(r"[^\w\s]", " ", title).split()
    all_words.extend(title_words)
    # Add keywords
    for item in keywords:
        words = item.replace("-", " ").replace("_", " ").split()
        all_words.extend(words)
    
    # Filter: lowercase, dedupe, length > 3, exclude common stop words
    STOP_WORDS = {"live", "updates", "today", "news", "latest"}
    return list(set(
        w.lower() for w in all_words 
        if len(w) > 3 and w.lower() not in STOP_WORDS
    ))

# NEET UG example
t1 = "NEET UG 2026 LIVE Updates: Minister refuses to take question"
k1 = ["NEET UG 2026", "Minister"]

t2 = "NEET UG 2026 Exam Cancelled LIVE: 'Guess Papers' First Dist"
k2 = ["NEET UG 2026", "Exam Cancelled"]

jk1 = build_jaccard_keywords_improved(t1, k1)
jk2 = build_jaccard_keywords_improved(t2, k2)
score = jaccard(jk1, jk2)

print(f"NEET UG with Title words:")
print(f"  Score: {score:.2f}")
print(f"  JK1: {jk1}")
print(f"  JK2: {jk2}")

# Alia Bhatt example
t3 = "Alia Bhatt Captures The Audrey Hepburn-Spirit In A Voluminou"
k3 = ["Alia Bhatt", "Audrey Hepburn"]

t4 = "Alia Bhatt makes first appearance at Cannes 2026, check out"
k4 = ["Alia Bhatt", "Cannes 2026"]

jk3 = build_jaccard_keywords_improved(t3, k3)
jk4 = build_jaccard_keywords_improved(t4, k4)
score_alia = jaccard(jk3, jk4)

print(f"\nAlia Bhatt with Title words:")
print(f"  Score: {score_alia:.2f}")
print(f"  JK3: {jk3}")
print(f"  JK4: {jk4}")
