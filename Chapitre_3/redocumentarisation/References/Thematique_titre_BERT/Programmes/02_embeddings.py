"""
02_embeddings.py — Encodage des documents avec all-mpnet-base-v2.

MODÈLE D'EMBEDDING : all-mpnet-base-v2
  - Song et al. (2020) : architecture MPNet, optimisée pour la similarité
    sémantique au niveau de la phrase (textes courts).
  - Reimers & Gurevych (2019) : Sentence-BERT, cadre général des modèles
    d'encodage de phrases par transformeurs siamois.
  - Choix empiriquement validé sur le corpus (voir comparaison SPECTER vs
    MPNet, K ∈ {30,35,40}) : MPNet supérieur sur Silhouette, CH, DB et ARI.

normalize_embeddings=True : projection sur hypersphère unitaire →
cohérent avec metric="cosine" dans UMAP.

Input  : docs_cache2.npy
Output : embeddings_cache.npy
"""

import numpy as np
from sentence_transformers import SentenceTransformer
from config import *

docs = list(np.load(DOCS_CACHE, allow_pickle=True))

if os.path.exists(EMBED_CACHE):
    print("Embeddings trouvés en cache → chargement...")
    embeddings = np.load(EMBED_CACHE)
else:
    print("Calcul des embeddings (tokens originaux → BERT)...")
    embed_model = SentenceTransformer(EMBED_MODEL)
    embeddings  = embed_model.encode(
        docs,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    np.save(EMBED_CACHE, embeddings)
    print("Embeddings sauvegardés en cache.")

print(f"Embeddings shape : {embeddings.shape}")
