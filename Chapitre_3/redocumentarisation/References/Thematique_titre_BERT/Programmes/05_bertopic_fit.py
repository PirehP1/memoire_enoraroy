"""
05_bertopic_fit.py — Fit BERTopic final (Ward) + métriques et topics avant fusion.

MODÈLE BERTOPIC FINAL
  BERTopic reçoit :
    embedding_model : MPNet (pour les futurs appels internes)
    umap_model      : UMAP avec n_components=5 (remplace le défaut n_components=2)
    hdbscan_model   : on substitue Ward à HDBSCAN — BERTopic accepte n'importe
                      quel objet sklearn avec fit_predict()
    vectorizer_model: notre CountVectorizer avec lemmes + bigrammes

  fit_transform(docs, embeddings) :
    - docs        : tokens originaux (embeddings pré-calculés fournis)
    - embeddings  : pré-calculés en 02_embeddings.py sur tokens originaux

  Première update_topics() sans topics= : recalcul c-TF-IDF sur labels
  ORIGINAUX (avant fusion) → pour inspecter les topics.

LEMMATISATION DIFFÉRENCIÉE
  - Inspection du JSON SpaCy : champ "lemma" renseigné uniquement pour les
    entités nommées reconnues (LOC, ORG, DATE) ; vide pour les tokens communs.
  - docs → tokens originaux → BERT :
    Les transformeurs gèrent nativement la variation morphologique via BPE
    (Reimers & Gurevych, 2019). La lemmatisation préalable est contre-
    productive : elle prive le modèle d'informations contextuelles.
  - docs_ctfidf → lemme si disponible (entités nommées), sinon token :
    Normalisation partielle réservée à l'étape c-TF-IDF (CountVectorizer).
    Améliore la discrimination lexicale inter-topics sans dégrader les
    embeddings (Grootendorst, 2022).

MÉTRIQUES AVANT FUSION
  Calculées sur umap_embeddings (espace dans lequel Ward a été appliqué),
  non sur les embeddings 768d (incohérence géométrique après réduction).

CLUSTERING : Ward hiérarchique agglomératif
  - Ward (1963) : minimise la variance intra-cluster à chaque fusion →
    clusters compacts et homogènes.
  - Déterministe → reproductibilité, contrairement à HDBSCAN.
  - Nombre de topics explicite → pas de paramètre de densité à régler.
  - HDBSCAN rejeté : produit un cluster dominant (>90% du corpus),
    incompatible avec la cartographie disciplinaire visée.
  - metric="euclidean" : contrainte sklearn pour linkage="ward".

Inputs  : docs_cache2.npy, docs_ctfidf_cache2.npy, embeddings_cache.npy,
          umap_embeddings_cache.npy, best_n.json, stop_words_english.txt
Outputs : metrics_before_merge.csv, topic_coherence_before_merge.csv,
          document_topics_before_merge.csv, bertopic_model_before_merge/
"""

import json
import numpy as np
import pandas as pd
import umap
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

UMAP_CACHE = os.path.join(OUTPUT_DIR, "umap_embeddings_cache.npy")

# ── Chargement des données ────────────────────────────────────────────────────

docs        = list(np.load(DOCS_CACHE,        allow_pickle=True))
doc_ids     = list(np.load(IDS_CACHE,         allow_pickle=True))
docs_ctfidf = list(np.load(DOCS_CTFIDF_CACHE, allow_pickle=True))
embeddings  = np.load(EMBED_CACHE) #ici les embeddings
umap_embeddings = np.load(UMAP_CACHE) #là on charge la réduction UMAP

with open(os.path.join(OUTPUT_DIR, "best_n.json")) as f:
    best_n = json.load(f)["best_n"]
print(f"best_n chargé : {best_n}")

# ── Vectorizer avec stopwords ─────────────────────────────────────────────────
# Appliqué sur docs_ctfidf (normalisation partielle lemmes/tokens).
# min_df=5 : ignore les termes présents dans moins de 5 documents.
# max_df=0.85 : ignore les termes présents dans plus de 85% des documents.
# ngram_range=(1, 2) : unigrammes et bigrammes.

if os.path.exists(STOPWORDS_PATH):
    with open(STOPWORDS_PATH, "r", encoding="utf-8") as f:
        custom_stopwords = [w.strip() for w in f if w.strip()]
    print(f"  {len(custom_stopwords)} stopwords chargés.")
else:
    custom_stopwords = "english"
    print("  Fallback sklearn 'english'.")

vectorizer = CountVectorizer(
    stop_words=custom_stopwords,
    min_df=5,
    max_df=0.85,
    ngram_range=(1, 2),
)

# ── Fit BERTopic ──────────────────────────────────────────────────────────────

print(f"\nFitting BERTopic final avec Ward (n_clusters={best_n})...")

#clustering hiérarchique avec Ward plutôt que HDBSCAN

embed_model_final = SentenceTransformer(EMBED_MODEL)
best_ward = AgglomerativeClustering(
    n_clusters=best_n, linkage="ward", metric=WARD_METRIC #nb de k choisi du coup
)

model = BERTopic(
    embedding_model=embed_model_final, #le modèle d'embedding retenu
    umap_model=umap.UMAP(random_state=RANDOM_STATE, **UMAP_PARAMS),
    hdbscan_model=best_ward, #ici du coup ward
    vectorizer_model=vectorizer,
    calculate_probabilities=False,
    verbose=True,
)
#apprentissage et assignation des topics
topics, _ = model.fit_transform(docs, embeddings)

print("\nMise à jour c-TF-IDF initiale (docs_ctfidf, labels originaux)...")
model.update_topics(docs_ctfidf, vectorizer_model=vectorizer, top_n_words=TOP_N_WORDS)

# ── Métriques avant fusion ────────────────────────────────────────────────────
# Calculées sur umap_embeddings (espace de référence du clustering Ward),
# PAS sur les embeddings 768d. Cohérence géométrique : Ward a opéré dans
# cet espace, donc c'est là que les clusters sont définis.

topic_labels = np.array(topics)
mask_before  = topic_labels != -1

#calcul des scores
sil_f_umap = silhouette_score(umap_embeddings[mask_before], topic_labels[mask_before])
ch_f_umap  = calinski_harabasz_score(umap_embeddings[mask_before], topic_labels[mask_before])
db_f_umap  = davies_bouldin_score(umap_embeddings[mask_before], topic_labels[mask_before])

print(f"\nMétriques avant fusion (UMAP 5d — espace de référence) :")
print(f"  Silhouette       : {sil_f_umap:.4f}")
print(f"  Calinski-Harabasz: {ch_f_umap:.2f}")
print(f"  Davies-Bouldin   : {db_f_umap:.4f}")
print(f"  Num topics       : {best_n}")

pd.DataFrame([{
    "n_clusters":        best_n,
    "embedding_space":   "umap_5d",
    "Silhouette":        sil_f_umap,
    "Calinski_Harabasz": ch_f_umap,
    "Davies_Bouldin":    db_f_umap,
}]).to_csv(os.path.join(OUTPUT_DIR, "metrics_before_merge.csv"), index=False)

# ── Cohérence et topics avant fusion ─────────────────────────────────────────
# topic_counts compte les documents par topic à partir de la liste topics
# retournée par fit_transform() — utilisé aussi pour les tableaux de cohérence.

topic_counts = pd.Series(topics).value_counts().sort_index()

coherence_rows = []
for t, terms in model.get_topics().items():
    if t == -1:
        continue
    words = [w for w, _ in terms[:TOP_N_WORDS]]
    coherence_rows.append({
        "Topic":       t,
        "N_documents": topic_counts.get(t, 0),
        "Top_terms":   " | ".join(words),
    })

df_coherence = (
    pd.DataFrame(coherence_rows)
    .sort_values("Topic")
    .reset_index(drop=True)
)
df_coherence.to_csv(
    os.path.join(OUTPUT_DIR, "topic_coherence_before_merge.csv"), index=False
)
print("\nTop termes par topic AVANT fusion :")
print(df_coherence.to_string(index=False))
print(f"\nTotal documents assignés : {df_coherence['N_documents'].sum()} / {len(docs)}")

pd.DataFrame({
    "doc_id": doc_ids,
    "text":   docs,
    "topic":  topics,
}).to_csv(
    os.path.join(OUTPUT_DIR, "document_topics_before_merge.csv"),
    index=False, encoding="utf-8",
)

# ── Sauvegarde du modèle et des topics bruts ──────────────────────────────────

model.save(os.path.join(OUTPUT_DIR, "bertopic_model_before_merge"))
np.save(os.path.join(OUTPUT_DIR, "topics_before_merge.npy"), np.array(topics))

print("\n  → metrics_before_merge.csv")
print("  → topic_coherence_before_merge.csv")
print("  → document_topics_before_merge.csv")
print("  → bertopic_model_before_merge/")
print("  → topics_before_merge.npy")
