
def jaccard(a: list[str], b: list[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)

def build_jaccard_keywords_old(keywords: list[str]) -> list[str]:
    return list(set(
        w.lower() for w in keywords if len(w) > 3
    ))

def build_jaccard_keywords_new(keywords: list[str]) -> list[str]:
    all_words = []
    for item in keywords:
        words = item.replace("-", " ").replace("_", " ").split()
        all_words.extend(words)
    return list(set(
        w.lower() for w in all_words if len(w) > 3
    ))

# Example 1: NEET UG
k1 = ["NEET UG 2026", "LIVE Updates", "Minister"]
k2 = ["NEET UG 2026", "Exam Cancelled", "Guess Papers"]

jk1_old = build_jaccard_keywords_old(k1)
jk2_old = build_jaccard_keywords_old(k2)
score_old = jaccard(jk1_old, jk2_old)

jk1_new = build_jaccard_keywords_new(k1)
jk2_new = build_jaccard_keywords_new(k2)
score_new = jaccard(jk1_new, jk2_new)

print(f"NEET UG (Phrases vs Phrases):")
print(f"  Old score: {score_old:.2f} (keywords: {jk1_old} vs {jk2_old})")
print(f"  New score: {score_new:.2f} (keywords: {jk1_new} vs {jk2_new})")

# Example: One source uses phrases, another uses words
k3 = ["NEET", "UG", "2026", "Exam"]
jk3_old = build_jaccard_keywords_old(k3)
score_mixed = jaccard(jk1_old, jk3_old)
score_mixed_new = jaccard(jk1_new, jk3_old)

print(f"\nMixed (Phrases vs Words):")
print(f"  Old score: {score_mixed:.2f}")
print(f"  New score: {score_mixed_new:.2f}")
