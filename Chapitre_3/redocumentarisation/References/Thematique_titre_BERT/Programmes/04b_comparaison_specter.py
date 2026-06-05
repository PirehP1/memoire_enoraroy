"""
04b_comparaison_specter.py — Comparaison empirique SPECTER vs MPNet (optionnel).

Reproduit la phase de sélection du modèle d'embedding documentée dans le mémoire.
Sans effet sur les caches utilisés par 05–11 : les caches MPNet ne sont pas écrasés.

Phase 1 (sklearn brut) : grid search Ward comparatif.
  MPNet → relecture de ward_grid_search_fine.csv produit par 04 (pas de recalcul).
  SPECTER → embeddings + UMAP + grid search calculés ici, mis en cache séparément.

Phase 2 (BERTopic) : comparaison à K_COMPARE fixé (best_n MPNet par défaut).
  Les deux modèles sont ajustés avec le même K dans BERTopic.
  Les métriques sont calculées dans l'espace UMAP propre à chaque modèle.

Inputs  : ward_grid_search_fine.csv (04), umap_embeddings_cache.npy (03),
          docs_cache2.npy, docs_ctfidf_cache2.npy, best_n.json, stop_words_english.txt
Outputs : comparison_grid_search.csv, comparison_bertopic_K{K}.csv,
          comparison_topics_K{K}.csv, embeddings_specter_cache.npy,
          umap_specter_cache.npy
"""

import json
import numpy as np
import pandas as pd
import umap as umap_lib
from bertopic import BERTopic
from sentence_transformers import SentenceTransformer
from sklearn.cluster import AgglomerativeClustering
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.metrics import (
    silhouette_score,
    calinski_harabasz_score,
    davies_bouldin_score,
)
from config import *

# ── Paramètres locaux ─────────────────────────────────────────────────────────

SPECTER_MODEL       = "allenai-specter"
SPECTER_EMBED_CACHE = os.path.join(OUTPUT_DIR, "embeddings_specter_cache.npy")
SPECTER_UMAP_CACHE  = os.path.join(OUTPUT_DIR, "umap_specter_cache.npy")

with open(os.path.join(OUTPUT_DIR, "best_n.json")) as f:
    K_COMPARE = json.load(f)["best_n"]
print(f"K_COMPARE (best_n MPNet) : {K_COMPARE}")

# ── Chargement corpus et vectorizer ──────────────────────────────────────────

docs        = list(np.load(DOCS_CACHE,        allow_pickle=True))
docs_ctfidf = list(np.load(DOCS_CTFIDF_CACHE, allow_pickle=True))

if os.path.exists(STOPWORDS_PATH):
    with open(STOPWORDS_PATH, "r", encoding="utf-8") as f:
        custom_stopwords = [w.strip() for w in f if w.strip()]
else:
    custom_stopwords = "english"

vectorizer = CountVectorizer(
    stop_words=custom_stopwords,
    min_df=5, max_df=0.85, ngram_range=(1, 2),
)

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 1 — Grid search comparatif
# ══════════════════════════════════════════════════════════════════════════════

print("\n=== PHASE 1 — Grid search comparatif SPECTER vs MPNet ===")

# MPNet : relecture directe du CSV produit par 04 (pas de recalcul)
df_mpnet = pd.read_csv(os.path.join(OUTPUT_DIR, "ward_grid_search_fine.csv"))
df_mpnet.insert(0, "model", "MPNet")
print(f"[MPNet] Grid search rechargée depuis ward_grid_search_fine.csv "
      f"({len(df_mpnet)} valeurs de K)")

# SPECTER : embeddings
if os.path.exists(SPECTER_EMBED_CACHE):
    print("[SPECTER] Embeddings en cache → chargement...")
    specter_embeddings = np.load(SPECTER_EMBED_CACHE)
else:
    print(f"[SPECTER] Calcul des embeddings ({SPECTER_MODEL})...")
    specter_embeddings = SentenceTransformer(SPECTER_MODEL).encode(
        docs, show_progress_bar=True, convert_to_numpy=True,
        normalize_embeddings=True,
    )
    np.save(SPECTER_EMBED_CACHE, specter_embeddings)

# SPECTER : UMAP
if os.path.exists(SPECTER_UMAP_CACHE):
    print("[SPECTER] UMAP en cache → chargement...")
    specter_umap = np.load(SPECTER_UMAP_CACHE)
else:
    print("[SPECTER] Réduction UMAP...")
    specter_umap = umap_lib.UMAP(
        random_state=RANDOM_STATE, **UMAP_PARAMS
    ).fit_transform(specter_embeddings)
    np.save(SPECTER_UMAP_CACHE, specter_umap)

# SPECTER : grid search Ward
print(f"[SPECTER] Grid search Ward (K ∈ {N_CLUSTERS_GRID[0]}–{N_CLUSTERS_GRID[-1]})...")
specter_results = []
for n in N_CLUSTERS_GRID:
    labels = AgglomerativeClustering(
        n_clusters=n, linkage="ward", metric=WARD_METRIC
    ).fit_predict(specter_umap)
    specter_results.append({
        "model":             "SPECTER",
        "n_clusters":        n,
        "Silhouette":        round(silhouette_score(specter_umap, labels), 4),
        "Calinski_Harabasz": round(calinski_harabasz_score(specter_umap, labels), 2),
        "Davies_Bouldin":    round(davies_bouldin_score(specter_umap, labels), 4),
    })
    r = specter_results[-1]
    print(f"  [SPECTER] n={n:3d} | Sil={r['Silhouette']:.4f} | "
          f"CH={r['Calinski_Harabasz']:.1f} | DB={r['Davies_Bouldin']:.4f}")

df_specter = pd.DataFrame(specter_results)
df_specter["rank_sil"] = df_specter["Silhouette"].rank(ascending=False)
df_specter["rank_ch"]  = df_specter["Calinski_Harabasz"].rank(ascending=False)
df_specter["rank_db"]  = df_specter["Davies_Bouldin"].rank(ascending=True)
df_specter["rank_sum"] = (df_specter["rank_sil"] + df_specter["rank_ch"]
                          + df_specter["rank_db"])

pd.concat([df_mpnet, df_specter], ignore_index=True).to_csv(
    os.path.join(OUTPUT_DIR, "comparison_grid_search.csv"), index=False
)

print("\n── Résumé rang agrégé phase 1 ──")
for label, df in [("MPNet", df_mpnet), ("SPECTER", df_specter)]:
    best = df.loc[df["rank_sum"].idxmin()]
    print(f"  {label:8s} | best K={int(best['n_clusters']):3d} | "
          f"Sil={best['Silhouette']:.4f} | CH={best['Calinski_Harabasz']:.1f} | "
          f"DB={best['Davies_Bouldin']:.4f} | rang={best['rank_sum']:.1f}")

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 2 — Comparaison BERTopic à K_COMPARE fixé
# ══════════════════════════════════════════════════════════════════════════════

print(f"\n=== PHASE 2 — Comparaison BERTopic à K={K_COMPARE} ===")

def fit_bertopic_compare(embeddings, umap_emb, model_name, label, k):
    """Fit BERTopic, retourne (dict métriques, df topics)."""
    ward = AgglomerativeClustering(n_clusters=k, linkage="ward", metric=WARD_METRIC)
    bt   = BERTopic(
        embedding_model=SentenceTransformer(model_name),
        umap_model=umap_lib.UMAP(random_state=RANDOM_STATE, **UMAP_PARAMS),
        hdbscan_model=ward,
        vectorizer_model=vectorizer,
        calculate_probabilities=False,
        verbose=False,
    )
    topics, _ = bt.fit_transform(docs, embeddings)
    bt.update_topics(docs_ctfidf, vectorizer_model=vectorizer, top_n_words=TOP_N_WORDS)

    arr  = np.array(topics)
    mask = arr != -1
    sil  = silhouette_score(umap_emb[mask], arr[mask])
    ch   = calinski_harabasz_score(umap_emb[mask], arr[mask])
    db   = davies_bouldin_score(umap_emb[mask], arr[mask])
    print(f"[{label}] Sil={sil:.4f}  CH={ch:.2f}  DB={db:.4f}")

    counts = pd.Series(topics).value_counts().sort_index()
    rows   = [
        {"model": label, "topic": t, "n_docs": counts.get(t, 0),
         "top_terms": " | ".join([w for w, _ in terms[:8]])}
        for t, terms in bt.get_topics().items() if t != -1
    ]
    return (
        {"model": label, "K": k, "Silhouette": round(sil, 4),
         "Calinski_Harabasz": round(ch, 2), "Davies_Bouldin": round(db, 4)},
        pd.DataFrame(rows),
    )

mpnet_umap = np.load(os.path.join(OUTPUT_DIR, "umap_embeddings_cache.npy"))
mpnet_embeddings = np.load(EMBED_CACHE)

m_mpnet,   t_mpnet   = fit_bertopic_compare(
    mpnet_embeddings, mpnet_umap,    EMBED_MODEL,    "MPNet",   K_COMPARE)
m_specter, t_specter = fit_bertopic_compare(
    specter_embeddings, specter_umap, SPECTER_MODEL, "SPECTER", K_COMPARE)

pd.DataFrame([m_mpnet, m_specter]).to_csv(
    os.path.join(OUTPUT_DIR, f"comparison_bertopic_K{K_COMPARE}.csv"), index=False)
pd.concat([t_mpnet, t_specter], ignore_index=True).to_csv(
    os.path.join(OUTPUT_DIR, f"comparison_topics_K{K_COMPARE}.csv"), index=False)

print(f"\n  → comparison_grid_search.csv")
print(f"  → comparison_bertopic_K{K_COMPARE}.csv")
print(f"  → comparison_topics_K{K_COMPARE}.csv")