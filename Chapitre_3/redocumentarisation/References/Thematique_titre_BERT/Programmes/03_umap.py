"""
03_umap.py — Réduction dimensionnelle UMAP (pré-calcul pour la grid search Ward).

RÉDUCTION DIMENSIONNELLE : UMAP
  - McInnes et al. (2018) : UMAP préserve les structures locales ET globales
    du manifold, avec performances computationnelles supérieures à t-SNE.
  - n_components=5 : valeur recommandée par Grootendorst (2022) pour le
    clustering dans BERTopic (compromis réduction/préservation d'information).
    NB : sans spécification, umap.UMAP() utilise n_components=2 (visualisation),
    sous-optimal pour le clustering.
  - n_neighbors=15 : équilibre structure locale/globale (McInnes et al., 2018).
  - min_dist=0.1 : regroupements locaux denses, séparation inter-clusters
    préservée (McInnes et al., 2018).
  - metric="cosine" : standard pour embeddings de transformeurs normalisés
    (normalize_embeddings=True) ; distance euclidienne moins discriminante
    en haute dimension (Chang et al., 2025).
  - random_state=42 : reproductibilité garantie.

NB : BERTopic appliquera son propre UMAP interne (mêmes paramètres).
Ce pré-calcul sert à la grid search et aux métriques post-fusion.

Input  : embeddings_cache.npy
Output : umap_embeddings_cache.npy
"""

import numpy as np
import umap
from config import *

UMAP_CACHE = os.path.join(OUTPUT_DIR, "umap_embeddings_cache.npy")

embeddings = np.load(EMBED_CACHE)

#pour ne pas recalculer le UMAP au cas où
if os.path.exists(UMAP_CACHE):
    print("UMAP trouvé en cache → chargement...")
    umap_embeddings = np.load(UMAP_CACHE)
else:
    print("Réduction UMAP (pré-calcul pour grid search)...")
    # Création du modèle UMAP avec paramètres définis dans config.py
    # RANDOM_STATE : garantit reproductibilité des projections
    # **UMAP_PARAMS : injecte n_neighbors, min_dist, n_components, metric, etc.
    reducer = umap.UMAP(random_state=RANDOM_STATE, **UMAP_PARAMS)
    # Apprentissage + projection des embeddings dans un espace réduit (ex: 768 → 5)
    umap_embeddings = reducer.fit_transform(embeddings)
    np.save(UMAP_CACHE, umap_embeddings)
    print("UMAP sauvegardé en cache.")

print(f"UMAP shape : {umap_embeddings.shape}")
