"""
11_discriminant_terms.py — Top 15 termes c-TF-IDF par topic (après fusion).

Lit directement les scores c-TF-IDF calculés par BERTopic via get_topics().
Aucune re-vectorisation : cohérence garantie avec le modèle final.

Input  : bertopic_model_after_merge/
Output : topic_top15_ctfidf.csv
"""

import pandas as pd
from bertopic import BERTopic
from config import *

model = BERTopic.load(os.path.join(OUTPUT_DIR, "bertopic_model_after_merge"))

rows = []
for topic_id, terms in model.get_topics().items():
    if topic_id == -1:
        continue
    for rank, (word, score) in enumerate(terms[:15], start=1):
        rows.append({
            "topic": topic_id,
            "rank":  rank,
            "term":  word,
            "ctfidf_score": round(score, 6),
        })

df = pd.DataFrame(rows).sort_values(["topic", "rank"]).reset_index(drop=True)
df.to_csv(os.path.join(OUTPUT_DIR, "topic_top15_ctfidf.csv"), index=False)

print(df.to_string(index=False))
print(f"\n→ topic_top15_ctfidf.csv ({len(df)} lignes, {df['topic'].nunique()} topics)")