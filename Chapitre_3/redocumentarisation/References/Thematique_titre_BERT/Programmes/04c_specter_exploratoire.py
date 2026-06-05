"""
04c_specter_exploratoire.py — Exploration SPECTER à son optimum naturel (K=14).

Fit BERTopic avec SPECTER + Ward à K=14 (optimum rang agrégé issu de
comparison_grid_search.csv) et affiche les topics pour évaluation qualitative.

Sans effet sur les caches MPNet : aucun fichier utilisé par 05–11 n'est modifié.

Inputs  : docs_cache2.npy, docs_ctfidf_cache2.npy,
          embeddings_specter_cache.npy, umap_specter_cache.npy,
          stop_words_english.txt
Output  : specter_topics_K14.csv
"""

import numpy as np
import pandas as pd
import umap as umap_lib
from bertopic import BERTopic
from sentence_transformers import SentenceTransformer
from sklearn.cluster import AgglomerativeClustering
from sklearn.feature_extraction.text import CountVectorizer
from config import *

# ── Paramètres ────────────────────────────────────────────────────────────────

SPECTER_MODEL      = "allenai-specter"
SPECTER_EMBED_CACHE = os.path.join(OUTPUT_DIR, "embeddings_specter_cache.npy")
SPECTER_UMAP_CACHE  = os.path.join(OUTPUT_DIR, "umap_specter_cache.npy")
K_SPECTER          = 14   # optimum rang agrégé SPECTER (comparison_grid_search.csv)

# ── Chargement ────────────────────────────────────────────────────────────────

docs        = list(np.load(DOCS_CACHE,        allow_pickle=True))
docs_ctfidf = list(np.load(DOCS_CTFIDF_CACHE, allow_pickle=True))

if not os.path.exists(SPECTER_EMBED_CACHE) or not os.path.exists(SPECTER_UMAP_CACHE):
    raise FileNotFoundError(
        "Caches SPECTER absents. Lancer 04b_compare_embeddings.py d'abord."
    )

specter_embeddings = np.load(SPECTER_EMBED_CACHE)
specter_umap       = np.load(SPECTER_UMAP_CACHE)
print(f"Caches SPECTER chargés. Embeddings : {specter_embeddings.shape}")

if os.path.exists(STOPWORDS_PATH):
    with open(STOPWORDS_PATH, "r", encoding="utf-8") as f:
        custom_stopwords = [w.strip() for w in f if w.strip()]
else:
    custom_stopwords = "english"

vectorizer = CountVectorizer(
    stop_words=custom_stopwords,
    min_df=5, max_df=0.85, ngram_range=(1, 2),
)

# ── Fit BERTopic ──────────────────────────────────────────────────────────────

print(f"\nFit BERTopic SPECTER K={K_SPECTER}...")

model = BERTopic(
    embedding_model=SentenceTransformer(SPECTER_MODEL),
    umap_model=umap_lib.UMAP(random_state=RANDOM_STATE, **UMAP_PARAMS),
    hdbscan_model=AgglomerativeClustering(
        n_clusters=K_SPECTER, linkage="ward", metric=WARD_METRIC
    ),
    vectorizer_model=vectorizer,
    calculate_probabilities=False,
    verbose=False,
)
topics, _ = model.fit_transform(docs, specter_embeddings)
model.update_topics(docs_ctfidf, vectorizer_model=vectorizer, top_n_words=TOP_N_WORDS)

# ── Affichage console ─────────────────────────────────────────────────────────

topic_counts = pd.Series(topics).value_counts().sort_index()

print(f"\n{'='*60}")
print(f"SPECTER — BERTopic K={K_SPECTER} — top {TOP_N_WORDS} termes c-TF-IDF")
print(f"{'='*60}")

rows = []
for t, terms in sorted(model.get_topics().items()):
    if t == -1:
        continue
    n    = topic_counts.get(t, 0)
    pct  = 100 * n / len(docs)
    words = " | ".join([w for w, _ in terms[:TOP_N_WORDS]])
    print(f"\nTopic {t:2d}  ({n:5d} docs, {pct:.1f}%)")
    print(f"  {words}")
    rows.append({
        "topic":    t,
        "n_docs":   n,
        "pct":      round(pct, 2),
        "top_terms": words,
    })

# ── Export CSV ────────────────────────────────────────────────────────────────

out = os.path.join(OUTPUT_DIR, f"specter_topics_K{K_SPECTER}.csv")
pd.DataFrame(rows).to_csv(out, index=False)

print(f"\n{'='*60}")
print(f"Total assignés : {topic_counts.sum()} / {len(docs)}")
print(f"→ specter_topics_K{K_SPECTER}.csv")