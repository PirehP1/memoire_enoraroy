"""
09_metrics_final.py — Métriques Silhouette/CH/DB avant et après fusion (UMAP 5d).

MÉTRIQUES POST-FUSION
  Calculées sur umap_embeddings (espace dans lequel Ward a été appliqué),
  non sur les embeddings 768d (incohérence géométrique après réduction).
  Cohérence géométrique : Ward a opéré dans cet espace, donc c'est là que
  les clusters sont définis. Calculer sur 768d après coup n'aurait pas de sens.

Inputs  : umap_embeddings_cache.npy, topics_before_merge.npy,
          topics_after_merge.npy, metrics_before_merge.csv,
          best_n.json, n_after.json
Output  : metrics_after_merge.csv
"""

import json
import numpy as np
import pandas as pd
from sklearn.metrics import (
    silhouette_score,
    calinski_harabasz_score,
    davies_bouldin_score,
)
from config import *

UMAP_CACHE = os.path.join(OUTPUT_DIR, "umap_embeddings_cache.npy")

# ── Chargement ────────────────────────────────────────────────────────────────

umap_embeddings = np.load(UMAP_CACHE)
topics          = list(np.load(os.path.join(OUTPUT_DIR, "topics_before_merge.npy")))
topics_after    = np.load(os.path.join(OUTPUT_DIR, "topics_after_merge.npy"))

with open(os.path.join(OUTPUT_DIR, "best_n.json")) as f:
    best_n = json.load(f)["best_n"]
with open(os.path.join(OUTPUT_DIR, "n_after.json")) as f:
    n_after = json.load(f)["n_after"]

# Métriques avant fusion (relecture depuis le CSV produit en 05)
df_before = pd.read_csv(os.path.join(OUTPUT_DIR, "metrics_before_merge.csv"))
sil_f_umap = df_before["Silhouette"].iloc[0]
ch_f_umap  = df_before["Calinski_Harabasz"].iloc[0]
db_f_umap  = df_before["Davies_Bouldin"].iloc[0]

# ── Métriques après fusion ────────────────────────────────────────────────────

labels_r = np.array(topics_after)
mask_r   = labels_r != -1

if mask_r.sum() > 0 and len(set(labels_r[mask_r])) > 1:

    sil_r = silhouette_score(umap_embeddings[mask_r], labels_r[mask_r])
    ch_r  = calinski_harabasz_score(umap_embeddings[mask_r], labels_r[mask_r])
    db_r  = davies_bouldin_score(umap_embeddings[mask_r], labels_r[mask_r])

    print(f"\nMétriques AVANT fusion (UMAP 5d) :")
    print(f"  Silhouette       : {sil_f_umap:.4f}")
    print(f"  Calinski-Harabasz: {ch_f_umap:.2f}")
    print(f"  Davies-Bouldin   : {db_f_umap:.4f}")

    print(f"\nMétriques APRÈS fusion (UMAP 5d — même espace) :")
    print(f"  Silhouette       : {sil_r:.4f}")
    print(f"  Calinski-Harabasz: {ch_r:.2f}")
    print(f"  Davies-Bouldin   : {db_r:.4f}")
    print(f"  Num topics       : {n_after}")

    pd.DataFrame([
        {
            "phase":             "before_merge",
            "n_clusters":        best_n,
            "embedding_space":   "umap_5d",
            "Silhouette":        sil_f_umap,
            "Calinski_Harabasz": ch_f_umap,
            "Davies_Bouldin":    db_f_umap,
        },
        {
            "phase":             "after_merge",
            "n_clusters":        n_after,
            "embedding_space":   "umap_5d",
            "Silhouette":        sil_r,
            "Calinski_Harabasz": ch_r,
            "Davies_Bouldin":    db_r,
        },
    ]).to_csv(os.path.join(OUTPUT_DIR, "metrics_after_merge.csv"), index=False)

    print("  → metrics_after_merge.csv")

else:
    print("  Pas assez de clusters distincts pour calculer les métriques après fusion.")
