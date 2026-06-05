"""
bertopic_pipeline.py
====================
Pipeline de topic modelling (BERTopic) sur un corpus de titres d'articles
académiques en anglais sur le Haut Moyen Âge.

Dépendances :
    pip install bertopic sentence-transformers umap-learn hdbscan
                scikit-learn gensim numpy pandas tqdm
"""

# =============================================================================
# PARAMÈTRES CONFIGURABLES
# =============================================================================

# -- Chemins
CORPUS_JSON        = "corpus.json"               # fichier JSON d'entrée
STOPWORDS_FILE     = "stop_words_english.txt"    # stopwords personnalisés (1 mot/ligne)
OUT_DOC_TOPICS     = "document_topics.csv"       # sortie : doc → topic
OUT_TOPIC_TERMS    = "topic_terms.csv"           # sortie : termes par topic

# -- Modèle d'embedding
# all-mpnet-base-v2 est le modèle par défaut recommandé par BERTopic ;
# il offre le meilleur compromis qualité/coût parmi les SentenceTransformers MPNET
# (score MTEB élevé, fenêtre de 384 tokens, suffisant pour des titres courts).
EMBEDDING_MODEL    = "sentence-transformers/all-mpnet-base-v2"

# -- Réduction dimensionnelle (UMAP)
# UMAP préserve mieux la structure locale/globale que PCA ou t-SNE,
# ce qui favorise des clusters compacts pour HDBSCAN.
UMAP_N_COMPONENTS  = 5      # dimensions cibles (5 est un bon compromis BERTopic)
UMAP_N_NEIGHBORS   = 15     # voisinage local ; augmenter pour des topics plus larges
UMAP_MIN_DIST      = 0.0    # 0.0 pousse les points similaires à se toucher → meilleurs clusters
UMAP_METRIC        = "cosine"
UMAP_RANDOM_STATE  = 42

# -- Clustering (HDBSCAN)
# HDBSCAN est non-paramétrique (pas besoin de fixer k a priori) et gère
# nativement le bruit (topic -1), ce qui le rend idéal pour des corpus hétérogènes.
HDBSCAN_MIN_CLUSTER_SIZE     = 30   # taille minimale d'un topic ; à adapter selon le corpus
HDBSCAN_MIN_SAMPLES          = 10   # contrôle la robustesse aux outliers
HDBSCAN_METRIC               = "euclidean"
HDBSCAN_CLUSTER_SELECTION    = "eom"  # "eom" = Excess of Mass, favorise les clusters compacts

# -- Vectorisation (c-TF-IDF)
CTFIDF_TOP_N_WORDS = 15     # nombre de termes caractéristiques retenus par topic
MIN_DF             = 2      # fréquence document minimale pour le vocabulaire

# -- Sweep du nombre de topics (BERTopic : nr_topics)
# On fait varier nr_topics pour observer l'évolution de la cohérence (Cv)
# et choisir le coude optimal avant surapprentissage thématique.
SWEEP_MIN_TOPICS   = 5
SWEEP_MAX_TOPICS   = 40
SWEEP_STEP         = 5

# -- Nombre de topics cible (fixé après analyse du sweep)
# Mettre None pour laisser HDBSCAN décider librement (mode auto-détection).
NR_TOPICS_FINAL    = None   # ex. : 20 → à renseigner après visualisation du sweep

# -- Cohérence (Gensim)
COHERENCE_METRIC   = "c_v"  # "c_v" est la métrique la plus corrélée au jugement humain


# =============================================================================
# IMPORTS
# =============================================================================

import json
import re
import numpy as np
import pandas as pd
from tqdm import tqdm

from sentence_transformers import SentenceTransformer
from umap import UMAP
from hdbscan import HDBSCAN
from sklearn.feature_extraction.text import CountVectorizer
from bertopic import BERTopic
from bertopic.vectorizers import ClassTfidfTransformer

import gensim.corpora as corpora
from gensim.models.coherencemodel import CoherenceModel

import matplotlib
matplotlib.use("Agg")              # backend sans affichage
import matplotlib.pyplot as plt


# =============================================================================
# 1. CHARGEMENT ET PRÉPARATION DU CORPUS
# =============================================================================

print("[1/6] Chargement du corpus JSON...")

with open(CORPUS_JSON, "r", encoding="utf-8") as f:
    raw = json.load(f)

# Charger les stopwords personnalisés
custom_stopwords = set()
try:
    with open(STOPWORDS_FILE, "r", encoding="utf-8") as f:
        custom_stopwords = {line.strip().lower() for line in f if line.strip()}
    print(f"    {len(custom_stopwords)} stopwords chargés depuis '{STOPWORDS_FILE}'")
except FileNotFoundError:
    print(f"    Avertissement : '{STOPWORDS_FILE}' introuvable — aucun stopword personnalisé.")

# Reconstruction des titres à partir des lemmes (tokens filtrés)
# On concatène les lemmes non-vides et hors-stopwords pour obtenir
# un texte normalisé mieux adapté à l'embedding et au c-TF-IDF.
doc_ids = []
titles_raw   = []   # titre brut (tokens originaux) → pour l'embedding
titles_lemma = []   # titre lemmatisé → pour le vocabulaire c-TF-IDF

for entry in tqdm(raw, desc="    Parsing JSON"):
    doc = entry["document"]
    doc_ids.append(doc["_id"])

    tokens_raw   = []
    tokens_lemma = []

    for feat in doc.get("lexical_features", []):
        token = feat.get("token", "").strip()
        lemma = feat.get("lemma", "").strip()

        # Conserver uniquement les tokens alphabétiques non vides
        if not token or not re.match(r"^[A-Za-z\-']+$", token):
            continue

        # Titre brut : utiliser le token tel quel
        tokens_raw.append(token)

        # Version lemmatisée : priorité au lemme, sinon au token ; tout en minuscules
        candidate = lemma if lemma else token
        if candidate.lower() not in custom_stopwords:
            tokens_lemma.append(candidate.lower())

    titles_raw.append(" ".join(tokens_raw))
    titles_lemma.append(" ".join(tokens_lemma))

print(f"    {len(titles_raw)} documents chargés.")


# =============================================================================
# 2. ENCODAGE DES TITRES (SENTENCE TRANSFORMERS — MPNET)
# =============================================================================

# all-mpnet-base-v2 produit des embeddings de 768 dimensions avec une
# représentation sémantique dense, supérieure aux approches bag-of-words
# pour des titres courts où le contexte est crucial.

print(f"\n[2/6] Encodage avec '{EMBEDDING_MODEL}'...")

embedding_model = SentenceTransformer(EMBEDDING_MODEL)
embeddings = embedding_model.encode(
    titles_raw,
    show_progress_bar=True,
    batch_size=64,
    normalize_embeddings=True   # cosine similarity ≡ produit scalaire après normalisation
)
embeddings = np.array(embeddings)
print(f"    Embeddings : {embeddings.shape}")


# =============================================================================
# 3. RÉDUCTION DIMENSIONNELLE (UMAP)
# =============================================================================

print("\n[3/6] Réduction dimensionnelle (UMAP)...")

umap_model = UMAP(
    n_components  = UMAP_N_COMPONENTS,
    n_neighbors   = UMAP_N_NEIGHBORS,
    min_dist      = UMAP_MIN_DIST,
    metric        = UMAP_METRIC,
    random_state  = UMAP_RANDOM_STATE,
    low_memory    = False
)
# Note : BERTopic appliquera UMAP en interne ; on le pré-instancie ici
# pour contrôler exactement les hyperparamètres et réutiliser les embeddings.


# =============================================================================
# 4. SWEEP DU NOMBRE DE TOPICS (COHÉRENCE c_v)
# =============================================================================
# Stratégie : entraîner BERTopic avec nr_topics fixé à différentes valeurs,
# puis calculer la cohérence Cv (Gensim) sur les top-N termes de chaque topic.
# On retient le nombre de topics correspondant au maximum (ou au coude) de Cv.
# Cette méthode est préférable à la perplexité (LDA) car elle corrèle mieux
# avec l'évaluation humaine de la qualité des topics.

print("\n[4/6] Sweep du nombre de topics...")

sweep_range      = list(range(SWEEP_MIN_TOPICS, SWEEP_MAX_TOPICS + 1, SWEEP_STEP))
sweep_coherences = []

# Vocabulaire partagé pour Gensim
tokenized_lemma = [t.split() for t in titles_lemma]
dictionary      = corpora.Dictionary(tokenized_lemma)

for n_topics in tqdm(sweep_range, desc="    Sweep nr_topics"):

    hdbscan_tmp = HDBSCAN(
        min_cluster_size  = HDBSCAN_MIN_CLUSTER_SIZE,
        min_samples       = HDBSCAN_MIN_SAMPLES,
        metric            = HDBSCAN_METRIC,
        cluster_selection_method = HDBSCAN_CLUSTER_SELECTION,
        prediction_data   = True
    )

    vectorizer_tmp = CountVectorizer(
        stop_words   = list(custom_stopwords) if custom_stopwords else "english",
        min_df       = MIN_DF,
        ngram_range  = (1, 2)
    )

    ctfidf_tmp = ClassTfidfTransformer(reduce_frequent_words=True)

    topic_model_tmp = BERTopic(
        embedding_model         = embedding_model,
        umap_model              = UMAP(
            n_components = UMAP_N_COMPONENTS,
            n_neighbors  = UMAP_N_NEIGHBORS,
            min_dist     = UMAP_MIN_DIST,
            metric       = UMAP_METRIC,
            random_state = UMAP_RANDOM_STATE
        ),
        hdbscan_model           = hdbscan_tmp,
        vectorizer_model        = vectorizer_tmp,
        ctfidf_model            = ctfidf_tmp,
        top_n_words             = CTFIDF_TOP_N_WORDS,
        nr_topics               = n_topics,
        verbose                 = False
    )

    topics_tmp, _ = topic_model_tmp.fit_transform(titles_raw, embeddings=embeddings)

    # Extraire les termes par topic pour Gensim
    topic_words_tmp = []
    for tid in set(topics_tmp):
        if tid == -1:
            continue
        terms = [w for w, _ in topic_model_tmp.get_topic(tid)]
        # Normaliser en tokens simples (supprimer les bigrammes pour Gensim)
        terms_simple = [t.split()[0] for t in terms if t]
        if terms_simple:
            topic_words_tmp.append(terms_simple)

    if len(topic_words_tmp) < 2:
        sweep_coherences.append(np.nan)
        continue

    cm = CoherenceModel(
        topics     = topic_words_tmp,
        texts      = tokenized_lemma,
        dictionary = dictionary,
        coherence  = COHERENCE_METRIC
    )
    sweep_coherences.append(cm.get_coherence())

# Visualisation du sweep
plt.figure(figsize=(10, 5))
plt.plot(sweep_range, sweep_coherences, marker="o", linewidth=2, color="#2C7BB6")
plt.xlabel("Nombre de topics (nr_topics)", fontsize=12)
plt.ylabel(f"Cohérence ({COHERENCE_METRIC.upper()})", fontsize=12)
plt.title("Évolution de la cohérence selon le nombre de topics", fontsize=13)
plt.xticks(sweep_range)
plt.grid(True, alpha=0.4)
plt.tight_layout()
plt.savefig("coherence_sweep.png", dpi=150)
plt.close()

best_idx       = int(np.nanargmax(sweep_coherences))
best_n_topics  = sweep_range[best_idx]
best_coherence = sweep_coherences[best_idx]
print(f"\n    Meilleur nr_topics : {best_n_topics}  (cohérence {COHERENCE_METRIC} = {best_coherence:.4f})")
print("    Courbe sauvegardée : coherence_sweep.png")

# Utiliser le paramètre manuel si renseigné, sinon le meilleur automatique
final_nr_topics = NR_TOPICS_FINAL if NR_TOPICS_FINAL is not None else best_n_topics
print(f"    nr_topics retenu pour le modèle final : {final_nr_topics}")


# =============================================================================
# 5. ENTRAÎNEMENT DU MODÈLE BERTOPIC FINAL
# =============================================================================

print(f"\n[5/6] Entraînement BERTopic final (nr_topics={final_nr_topics})...")

hdbscan_model = HDBSCAN(
    min_cluster_size         = HDBSCAN_MIN_CLUSTER_SIZE,
    min_samples              = HDBSCAN_MIN_SAMPLES,
    metric                   = HDBSCAN_METRIC,
    cluster_selection_method = HDBSCAN_CLUSTER_SELECTION,
    prediction_data          = True
)

vectorizer_model = CountVectorizer(
    stop_words  = list(custom_stopwords) if custom_stopwords else "english",
    min_df      = MIN_DF,
    ngram_range = (1, 2)   # unigrammes + bigrammes pour capturer "early medieval", etc.
)

ctfidf_model = ClassTfidfTransformer(
    reduce_frequent_words = True   # réduit le poids des termes très fréquents inter-topics
)

topic_model = BERTopic(
    embedding_model  = embedding_model,
    umap_model       = umap_model,
    hdbscan_model    = hdbscan_model,
    vectorizer_model = vectorizer_model,
    ctfidf_model     = ctfidf_model,
    top_n_words      = CTFIDF_TOP_N_WORDS,
    nr_topics        = final_nr_topics,
    verbose          = True
)

topics, probabilities = topic_model.fit_transform(titles_raw, embeddings=embeddings)

topic_info = topic_model.get_topic_info()
n_detected = len(topic_info[topic_info["Topic"] != -1])
n_outliers = sum(1 for t in topics if t == -1)
print(f"\n    Topics détectés (hors bruit) : {n_detected}")
print(f"    Documents non assignés (topic -1) : {n_outliers} "
      f"({100 * n_outliers / len(topics):.1f} %)")


# =============================================================================
# 6. EXPORT DES RÉSULTATS
# =============================================================================

print(f"\n[6/6] Export des résultats...")

# --- document_topics.csv : identifiant + topic assigné + label automatique
topic_labels = {
    row["Topic"]: row["Name"]
    for _, row in topic_info.iterrows()
}

df_docs = pd.DataFrame({
    "doc_id"      : doc_ids,
    "topic_id"    : topics,
    "topic_label" : [topic_labels.get(t, "Outlier") for t in topics],
    "probability" : [
        float(probabilities[i]) if probabilities is not None and hasattr(probabilities[i], "__float__")
        else np.nan
        for i in range(len(topics))
    ]
})
df_docs.to_csv(OUT_DOC_TOPICS, index=False, encoding="utf-8")
print(f"    {OUT_DOC_TOPICS} ({len(df_docs)} lignes)")

# --- topic_terms.csv : termes c-TF-IDF par topic
records = []
for _, row in topic_info.iterrows():
    tid = row["Topic"]
    if tid == -1:
        continue
    top_words = topic_model.get_topic(tid)  # liste de (term, score)
    for rank, (term, score) in enumerate(top_words, start=1):
        records.append({
            "topic_id"   : tid,
            "topic_label": row["Name"],
            "rank"       : rank,
            "term"       : term,
            "ctfidf_score": round(score, 6)
        })

df_terms = pd.DataFrame(records)
df_terms.to_csv(OUT_TOPIC_TERMS, index=False, encoding="utf-8")
print(f"    {OUT_TOPIC_TERMS} ({len(df_terms)} lignes, {df_terms['topic_id'].nunique()} topics)")

# --- Résumé textuel dans la console
print("\n" + "=" * 65)
print("RÉSUMÉ DES TOPICS (top 10 termes)")
print("=" * 65)
for _, row in topic_info[topic_info["Topic"] != -1].iterrows():
    tid   = row["Topic"]
    label = row["Name"]
    count = row["Count"]
    terms = ", ".join(w for w, _ in topic_model.get_topic(tid)[:10])
    print(f"\nTopic {tid:>3}  [{count:>5} docs]  {label}")
    print(f"         {terms}")

print("\nPipeline terminé. Fichiers générés :")
print(f"  - {OUT_DOC_TOPICS}")
print(f"  - {OUT_TOPIC_TERMS}")
print("  - coherence_sweep.png")
