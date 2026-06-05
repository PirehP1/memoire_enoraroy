"""
07_merge_topics.py — Fusion manuelle des topics + recalcul c-TF-IDF.

FUSION MANUELLE DES TOPICS
  - La fusion automatique reduce_topics() fusionne par similarité cosinus
    globale sur c-TF-IDF et peut fusionner des topics substantiels avant
    les clusters de bruit (Grootendorst, 2022).
  - Fusion manuelle guidée par deux critères quantitatifs :
    (a) Similarité cosinus entre topic embeddings (seuil ≥ 0.85)
    (b) Similarité de Jaccard sur les top-20 termes c-TF-IDF (validation)
    Cosinus élevé + Jaccard faible = similarité superficielle, non fusionné.
  - Conforme à Grimmer & Stewart (2013) : validation humaine indispensable.
  - Conforme à Maier et al. (2018) : interprétabilité = critère essentiel.

POINT CRITIQUE : update_topics() AVEC topics=list(topics_after)
  Sans ce paramètre, BERTopic recalcule c-TF-IDF sur les labels ORIGINAUX
  (best_n topics), et pas notre remapping. Avec topics=list(topics_after),
  il recalcule sur les labels fusionnés : le topic 18 agrège les documents
  des anciens topics 18+19+20+21+22+23+24, et son c-TF-IDF reflète
  correctement leur contenu combiné.

Inputs  : bertopic_model_before_merge/, topics_before_merge.npy,
          docs_ctfidf_cache2.npy, doc_ids_cache2.npy, docs_cache2.npy
Outputs : topic_coherence_after_merge.csv, document_topics_final.csv,
          topics_after_merge.npy, bertopic_model_after_merge/
"""

import json
import numpy as np
import pandas as pd
from bertopic import BERTopic
from sklearn.feature_extraction.text import CountVectorizer
from config import *

# ── Chargement ────────────────────────────────────────────────────────────────

model       = BERTopic.load(os.path.join(OUTPUT_DIR, "bertopic_model_before_merge"))
topics      = list(np.load(os.path.join(OUTPUT_DIR, "topics_before_merge.npy")))
docs        = list(np.load(DOCS_CACHE,        allow_pickle=True))
doc_ids     = list(np.load(IDS_CACHE,         allow_pickle=True))
docs_ctfidf = list(np.load(DOCS_CTFIDF_CACHE, allow_pickle=True))

with open(os.path.join(OUTPUT_DIR, "best_n.json")) as f:
    best_n = json.load(f)["best_n"]

# ── Vectorizer ────────────────────────────────────────────────────────────────

if os.path.exists(STOPWORDS_PATH):
    with open(STOPWORDS_PATH, "r", encoding="utf-8") as f:
        custom_stopwords = [w.strip() for w in f if w.strip()]
else:
    custom_stopwords = "english"

vectorizer = CountVectorizer(
    stop_words=custom_stopwords,
    min_df=5,
    max_df=0.85,
    ngram_range=(1, 2),
)

# ── Fusion manuelle ───────────────────────────────────────────────────────────

if not MERGE_MAP:
    print("\n  MERGE_MAP vide — aucune fusion effectuée.")
    topics_after = np.array(topics)
    n_after = best_n
else:
    print(f"\n=== Fusion manuelle des topics ({len(MERGE_MAP)} entrées) ===")
    topics_after = np.array([MERGE_MAP.get(t, t) for t in topics])
    n_after = len(set(topics_after)) - (1 if -1 in set(topics_after) else 0)
    print(f"  Topics avant fusion : {best_n}")
    print(f"  Topics après fusion : {n_after}")

    all_targets = sorted(set(MERGE_MAP.values()))
    for target in all_targets:
        merged_from = sorted([k for k, v in MERGE_MAP.items() if v == target])
        total_docs  = sum(1 for t in topics_after if t == target)
        print(f"  Topic {target:2d} ← {merged_from} | {total_docs} docs")

    # update_topics() AVEC topics=topics_after : CRITIQUE
    # Sans ce paramètre, BERTopic recalcule c-TF-IDF sur les labels ORIGINAUX,
    # ignorant le remapping manuel.
    print("\n  Recalcul c-TF-IDF sur labels fusionnés (topics=topics_after)...")
    model.update_topics(
        docs_ctfidf,
        topics=list(topics_after),
        vectorizer_model=vectorizer,
        top_n_words=TOP_N_WORDS,
    )
    print("  Done.")

# ── Cohérence et documents après fusion ───────────────────────────────────────

topic_counts_r = pd.Series(topics_after).value_counts().sort_index()

coherence_rows_r = []
for t, terms in model.get_topics().items():
    if t == -1:
        continue
    n_docs = topic_counts_r.get(t, 0)
    if n_docs == 0:
        continue
    words = [w for w, _ in terms[:TOP_N_WORDS]]
    coherence_rows_r.append({
        "Topic":       t,
        "N_documents": n_docs,
        "Top_terms":   " | ".join(words),
    })

df_coherence_r = (
    pd.DataFrame(coherence_rows_r)
    .sort_values("N_documents", ascending=False)
    .reset_index(drop=True)
)
df_coherence_r.to_csv(
    os.path.join(OUTPUT_DIR, "topic_coherence_after_merge.csv"), index=False
)
print(f"\nTopics après fusion ({len(df_coherence_r)} topics actifs) :")
print(df_coherence_r.to_string(index=False))
print(f"\nTotal documents : {topic_counts_r.sum()} / {len(docs)}")

pd.DataFrame({
    "doc_id":         doc_ids,
    "text":           docs,
    "text_ctfidf":    docs_ctfidf,
    "topic_original": topics,
    "topic_merged":   topics_after.tolist(),
}).to_csv(
    os.path.join(OUTPUT_DIR, "document_topics_final.csv"),
    index=False, encoding="utf-8",
)

# ── Sauvegarde ────────────────────────────────────────────────────────────────

model.save(os.path.join(OUTPUT_DIR, "bertopic_model_after_merge"))
np.save(os.path.join(OUTPUT_DIR, "topics_after_merge.npy"), topics_after)

with open(os.path.join(OUTPUT_DIR, "n_after.json"), "w") as f:
    json.dump({"n_after": n_after}, f)

print("\n  → topic_coherence_after_merge.csv")
print("  → document_topics_final.csv")
print("  → bertopic_model_after_merge/")
print("  → topics_after_merge.npy")
print("  → n_after.json")
