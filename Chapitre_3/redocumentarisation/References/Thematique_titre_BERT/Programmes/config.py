"""
config.py — Chemins, constantes, hyperparamètres, MERGE_MAP.
Importé par tous les scripts suivants via : from config_00 import *
"""

import os

# ── CHEMINS ───────────────────────────────────────────────────────────────────

BASE_PATH         = os.path.join(os.path.dirname(__file__), "..", "Données")
BASE_PATH         = os.path.normpath(BASE_PATH)
OUTPUT_DIR        = os.path.join(BASE_PATH, "bertopic_analysis")
INPUT_JSON        = os.path.join(BASE_PATH, "ref_anglais_local.json")
STOPWORDS_PATH    = os.path.join(BASE_PATH, "stop_words_english.txt")

# Caches disque — permettent de relancer depuis n'importe quelle étape
# sans recalculer les étapes précédentes (embeddings surtout, coûteux).
EMBED_CACHE       = os.path.join(OUTPUT_DIR, "embeddings_cache.npy")
IDS_CACHE         = os.path.join(OUTPUT_DIR, "doc_ids_cache2.npy")
DOCS_CACHE        = os.path.join(OUTPUT_DIR, "docs_cache2.npy")
DOCS_CTFIDF_CACHE = os.path.join(OUTPUT_DIR, "docs_ctfidf_cache2.npy")

# ── MODÈLE D'EMBEDDING ────────────────────────────────────────────────────────
# all-mpnet-base-v2 : choix empiriquement validé face à SPECTER
# sur le corpus (meilleur sur Silhouette, CH et DB pour K ∈ {30,35,40}).
# Réf. : Song et al. (2020) MPNet ; Reimers & Gurevych (2019) Sentence-BERT.
EMBED_MODEL = "sentence-transformers/all-mpnet-base-v2"

# ── UMAP ──────────────────────────────────────────────────────────────────────
# n_components=5 : valeur recommandée par Grootendorst (2022) pour le
# clustering dans BERTopic (compromis réduction/préservation d'information).
# NB : sans spécification, umap.UMAP() utilise n_components=2 (visualisation),
# sous-optimal pour le clustering.
# n_neighbors=15 : équilibre structure locale/globale (McInnes et al.,2020).
# min_dist=0.1 : regroupements locaux denses, séparation inter-clusters
# préservée (McInnes et al.,2020).
# metric="cosine" : standard pour embeddings de transformeurs normalisés
# (normalize_embeddings=True) ; distance euclidienne moins discriminante
# en haute dimension (Chang et al., 2025)

UMAP_PARAMS = dict(
    n_neighbors=15,
    n_components=5,
    min_dist=0.1,
    metric="cosine",
)

# ── CLUSTERING ────────────────────────────────────────────────────────────────
# Ward (1963) : minimise la variance intra-cluster à chaque fusion →
# clusters compacts et homogènes. Déterministe → reproductibilité.
# metric="euclidean" : contrainte sklearn pour linkage="ward".
WARD_METRIC  = "euclidean"
RANDOM_STATE = 42

# ── GRID SEARCH ───────────────────────────────────────────────────────────────
N_CLUSTERS_GRID = list(range(2, 41))

# ── BERTOPIC ──────────────────────────────────────────────────────────────────
TOP_N_WORDS = 20

# ── SIMILARITÉ / FUSION ───────────────────────────────────────────────────────
# Seuil de similarité cosinus pour le rapport des paires candidates à la fusion.
SIMILARITY_THRESHOLD = 0.15 #volontairement TRES bas car en fait les similarités sont assez faibles

# MERGE_MAP : fusions manuelles.
# Format : {topic_source: topic_cible}
# La cible reçoit les documents de la source.
#
# WORKFLOW : faire un premier run avec MERGE_MAP vide pour consulter les paires
# et la heatmap, puis inspecter les keywords, puis compléter.
MERGE_MAP = {
    # ── BRUIT ÉDITORIAL (18–24 → 18) ──────────────────────────────────────
    # Similarités cosinus avec topics substantiels : systématiquement < 0.40
    # Topics 20 et 21 : cosinus = 1.000 (clusters identiques, artefacts)
    # Topics 19, 22, 23 : vocabulaire éditorial de recensions
    # Topic 16 : bruit linguistique (articles français/italiens, noms propres)
    #            cosinus avec bruit éditorial (0.26-0.36) > cosinus avec
    #            topics substantiels (0.49 max mais termes non thématiques)
    # Voici l'exemple sur mon corpus
    #19: 18,
    #20: 18,
    #21: 18,
    #22: 18,
    #23: 18,
    #24: 18,
}

# Topics considérés comme bruit éditorial — exclus du rapport de similarité
# et de la cohérence C_V finale.
NOISE_TOPIC_IDS = set(range(18, 25)) #ici en question c'était parce que ces topics étaient du bruit

os.makedirs(OUTPUT_DIR, exist_ok=True)
