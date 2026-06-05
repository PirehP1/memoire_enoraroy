"""
04_grid_search.py — Sélection de K par rang agrégé multi-critères (Ward).

SÉLECTION DE K : rang agrégé multi-critères
  - Arbelaitz et al. (2013) : aucun indice unique ne domine dans tous les
    contextes ; Silhouette, CH et DB forment le groupe statistiquement
    supérieur, notamment avec Ward (fig. 9).
  - Silhouette (Rousseeuw, 1987) : cohésion et séparation locale ; robuste
    au bruit (Arbelaitz et al., 2013, fig. 8).
  - Calinski-Harabasz (1974) : rapport variance inter/intra-classe ; optimal
    en l'absence de bruit (Arbelaitz et al., 2013, fig. 8).
  - Davies-Bouldin (1979) : compacité relative des groupes.
  - Agrégation par rang : évite la sur-optimisation d'un critère unique,
    conforme à la recommandation multi-critères d'Arbelaitz et al. (2013).

Pour chaque valeur de K :
  - on applique Ward dans l'espace UMAP 5d
  - on calcule les trois indices de validité interne
Puis on sélectionne K par rang agrégé : chaque indice est classé
indépendamment, et on retient le K dont la somme des rangs est minimale.
Cela évite de sur-optimiser un seul critère (ex : CH croît mécaniquement
avec K, ce qui le rendrait trompeur seul).

Input  : umap_embeddings_cache.npy
Output : ward_grid_search_fine.csv

Le K retenu automatiquement est un optimum statistique. Si plusieurs valeurs de K présentent un rang agrégé proche, la sélection finale doit intégrer un critère d'interprétabilité (Grimmer & Stewart, 2013 ; Maier et al., 2018) : relancer 05_bertopic_fit.py avec best_n modifié manuellement dans best_n.json avant de poursuivre.
"""

import numpy as np
import pandas as pd
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics import (
    silhouette_score,
    calinski_harabasz_score,
    davies_bouldin_score,
)
from config import *

UMAP_CACHE = os.path.join(OUTPUT_DIR, "umap_embeddings_cache.npy")

umap_embeddings = np.load(UMAP_CACHE)

print("=== Grid search Ward (pas=1) ===")
results = []

for n in N_CLUSTERS_GRID:
    ward   = AgglomerativeClustering(n_clusters=n, linkage="ward", metric=WARD_METRIC)
    labels = ward.fit_predict(umap_embeddings)

    sil = silhouette_score(umap_embeddings, labels)
    ch  = calinski_harabasz_score(umap_embeddings, labels)
    db  = davies_bouldin_score(umap_embeddings, labels)

    results.append({
        "n_clusters":        n,
        "Silhouette":        round(sil, 4),
        "Calinski_Harabasz": round(ch, 2),
        "Davies_Bouldin":    round(db, 4),
    })
    print(f"  n={n:3d} | Sil={sil:.4f} | CH={ch:.1f} | DB={db:.4f}")

df_grid = pd.DataFrame(results)

# Rang agrégé : on classe les rangs selon les indicateurs.
# Le meilleur K est celui avec la somme des rangs minimale.
df_grid["rank_sil"] = df_grid["Silhouette"].rank(ascending=False)
df_grid["rank_ch"]  = df_grid["Calinski_Harabasz"].rank(ascending=False)
df_grid["rank_db"]  = df_grid["Davies_Bouldin"].rank(ascending=True)
df_grid["rank_sum"] = df_grid["rank_sil"] + df_grid["rank_ch"] + df_grid["rank_db"]

df_grid.to_csv(os.path.join(OUTPUT_DIR, "ward_grid_search_fine.csv"), index=False)

print(df_grid[["n_clusters", "Silhouette", "Calinski_Harabasz",
               "Davies_Bouldin", "rank_sum"]].to_string(index=False))

best_row = df_grid.loc[df_grid["rank_sum"].idxmin()]
best_n   = int(best_row["n_clusters"])
print(f"\nMeilleur n_clusters (rang agrégé) : {best_n}")
print(f"  Silhouette       : {best_row['Silhouette']}")
print(f"  Calinski-Harabasz: {best_row['Calinski_Harabasz']}")
print(f"  Davies-Bouldin   : {best_row['Davies_Bouldin']}")

# Sauvegarde du best_n pour les scripts suivants
import json
with open(os.path.join(OUTPUT_DIR, "best_n.json"), "w") as f:
    json.dump({"best_n": best_n}, f)
print(f"\nbest_n sauvegardé → best_n.json")
