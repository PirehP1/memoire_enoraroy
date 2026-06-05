# Pipeline de topic modelling BERTopic

Ce dossier regroupe les scripts utilisés pour identifier des thématiques dans un corpus de références bibliographiques en anglais, à partir d'un JSON SpaCy prétraité. Le pipeline repose sur BERTopic avec un clustering Ward hiérarchique substitué à HDBSCAN, choix motivé par la nécessité d'un nombre de topics explicite et d'une assignation déterministe de tous les documents.

Le pipeline se décompose en trois phases successives, dont seule la troisième est obligatoire pour reproduire les résultats finaux.

**Phase exploratoire (scripts `04b` et `04c`, optionnels)** : comparaison empirique des modèles d'embedding SPECTER et MPNet, sélection du modèle retenu pour le pipeline final. Ces scripts ne modifient aucun cache utilisé par la suite.

**Phase de sélection de K (scripts `01` à `04`, obligatoires)** : construction du corpus, encodage, réduction dimensionnelle, grid search multi-critères. Produit `best_n.json`, point d'entrée de la phase finale. Le K retenu automatiquement peut être modifié manuellement avant de poursuivre.

**Phase finale BERTopic (scripts `05` à `11`, obligatoires)** : fit du modèle, analyse de similarité, fusion manuelle des topics de bruit, évaluation, export.


Les scripts sont numérotés dans leur ordre d'exécution obligatoire. Chaque étape produit des fichiers cache ou intermédiaires qui permettent de relancer le pipeline depuis n'importe quel point sans recalculer les étapes précédentes — les embeddings en particulier sont coûteux.

---

Fichiers d'entrée attendus :

| Fichier | Description |
|---|---|
| `ref_anglais_local.json` | Corpus SpaCy : liste d'objets `{"document": {"_id": ..., "lexical_features": [...]}}`. Chaque token porte les champs `token`, `lemma`. |
| `stop_words_english.txt` | Liste de stopwords personnalisée, un mot par ligne. Fallback sur la liste sklearn `"english"` si absent. |

Fichiers de sortie principaux :

| Fichier | Produit par | Utilisé par |
|---|---|---|
| `docs_cache2.npy` | 01 | 02, 05 |
| `docs_ctfidf_cache2.npy` | 01 | 05, 07, 08, 11 |
| `doc_ids_cache2.npy` | 01 | 05, 07 |
| `embeddings_cache.npy` | 02 | 03, 05 |
| `umap_embeddings_cache.npy` | 03 | 04, 04b, 05, 09 |
| `ward_grid_search_fine.csv` | 04 | 04b |
| `best_n.json` | 04 | 04b, 04c, 05, 07, 08, 09 |
| `embeddings_specter_cache.npy` | 04b | 04c |
| `umap_specter_cache.npy` | 04b | 04c |
| `comparison_grid_search.csv` | 04b | — |
| `comparison_bertopic_K{K}.csv` | 04b | — |
| `comparison_topics_K{K}.csv` | 04b | — |
| `specter_topics_K14.csv` | 04c | — |
| `metrics_before_merge.csv` | 05 | 09 |
| `topic_coherence_before_merge.csv` | 05 | — |
| `document_topics_before_merge.csv` | 05 | — |
| `bertopic_model_before_merge/` | 05 | 06, 07 |
| `topics_before_merge.npy` | 05 | 06, 07, 09 |
| `topic_similarity_matrix.csv` | 06 | — |
| `topic_similar_pairs.csv` | 06 | — |
| `topic_jaccard_pairs.csv` | 06 | — |
| `topic_similarity_comparison.csv` | 06 | — |
| `topic_similarity_heatmap.pdf/png` | 06 | — |
| `hierarchy_before_merge.html` | 06 | — |
| `topic_coherence_after_merge.csv` | 07 | — |
| `document_topics_final.csv` | 07 | 11 |
| `bertopic_model_after_merge/` | 07 | 08, 09, 10, 11 |
| `topics_after_merge.npy` | 07 | 08, 09 |
| `n_after.json` | 07 | 08, 09, 10 |
| `coherence_after_merge.csv` | 08 | — |
| `metrics_after_merge.csv` | 09 | — |
| `barchart_final.pdf/html` | 10 | — |
| `hierarchy_final.pdf/html` | 10 | — |
| `bertopic_ward_model_final/` | 10 | — |
| `topic_top15_ctfidf.csv` | 11 | — |

--

## Description des scripts

### `config.py` — Chemins, hyperparamètres, MERGE_MAP

Importé par tous les scripts via `from config import *`. Centralise les chemins d'entrée/sortie, les paramètres UMAP (`n_neighbors=15`, `n_components=5`, `min_dist=0.1`, `metric="cosine"`), le modèle d'embedding (`all-mpnet-base-v2`), la grille de K pour la grid search (`range(2, 41)`), et la `MERGE_MAP` pour les fusions manuelles.

Le champ `NOISE_TOPIC_IDS` liste les topics considérés comme bruit éditorial ; ils sont exclus des calculs de similarité et de cohérence C_V. La `MERGE_MAP` est intentionnellement vide au premier run — elle est à compléter après inspection des outputs de `06`, avant de relancer depuis `07`.

---

### `01_load_corpus.py` — Chargement du JSON SpaCy et construction des corpus

Lit `ref_anglais_local.json` et construit deux versions du corpus. `docs` contient les tokens originaux en minuscules (filtrés alpha) : version destinée aux embeddings BERT, qui gèrent nativement la morphologie via BPE. `docs_ctfidf` contient le lemme SpaCy lorsqu'il est disponible, sinon le token original : version destinée au CountVectorizer et au c-TF-IDF.

Les trois caches sont systématiquement vérifiés à l'entrée ; si les trois sont présents, la construction est sautée.

Sorties : `docs_cache2.npy`, `docs_ctfidf_cache2.npy`, `doc_ids_cache2.npy`.

---

### `02_embeddings.py` — Encodage des documents

Encode `docs` avec `sentence-transformers/all-mpnet-base-v2`, retenu empiriquement face à SPECTER sur ce corpus (retenu à l'issue de la phase exploratoire).

Sorties : `embeddings_cache.npy`.

---

### `03_umap.py` — Réduction dimensionnelle UMAP

Réduit les embeddings à 5 dimensions avec UMAP. `n_components=5` est la valeur recommandée par Grootendorst (2022) pour le clustering dans BERTopic — sans spécification, UMAP utilise `n_components=2`, dimensionnalité optimale pour la visualisation mais sous-optimale pour le clustering. Ce pré-calcul sert à la grid search Ward (`04`) et aux métriques post-fusion (`09`) ; BERTopic applique son propre UMAP interne avec les mêmes paramètres lors du fit.

Sorties : `umap_embeddings_cache.npy`.

---

### `04_grid_search.py` — Sélection de K par rang agrégé multi-critères

Évalue Ward pour chaque K dans `N_CLUSTERS_GRID` (`range(2, 41)` par défaut) sur les embeddings UMAP 5d. Calcule trois indices de validité interne — Silhouette (Rousseeuw, 1987), Calinski-Harabasz (1974), Davies-Bouldin (1979) — puis sélectionne le K dont la somme des rangs est minimale, conformément à la recommandation multi-critères d'Arbelaitz et al. (2013). L'agrégation par rang évite de sur-optimiser un critère unique (CH croît mécaniquement avec K, ce qui le rendrait trompeur seul).

> Note méthodologique : le K retenu automatiquement est un optimum statistique. Si plusieurs valeurs de K présentent un rang agrégé proche, la sélection finale doit intégrer un critère d'interprétabilité (Grimmer & Stewart, 2013 ; Maier et al., 2018). Dans ce cas, modifier `best_n` manuellement dans `best_n.json` avant de lancer `05`.

Sorties : `ward_grid_search_fine.csv`, `best_n.json`.

---

### `04b_compare_embeddings.py` — Comparaison empirique SPECTER vs MPNet *(optionnel)*

Script exploratoire reproduisant la phase de sélection du modèle d'embedding. Sans effet sur les caches MPNet utilisés par `05`–`11`.

**Phase 1 — grid search comparatif (sklearn brut).** MPNet réutilise `ward_grid_search_fine.csv` produit par `04` (pas de recalcul). SPECTER est encodé, réduit par UMAP et évalué sur la même grille, avec ses propres caches séparés. Sur ce corpus, SPECTER présente des valeurs de CH supérieures à MPNet sur toute la grille, mais une Silhouette inférieure à partir de K=6 — les espaces UMAP n'étant pas isométriques, cette comparaison directe des métriques n'est pas strictement valide et doit être interprétée avec précaution.

**Phase 2 — comparaison BERTopic à K fixé.** Les deux modèles sont ajustés dans BERTopic avec `K_COMPARE` (initialisé à `best_n` MPNet, modifiable en tête de script). Produit un tableau comparatif de métriques et les top-8 termes c-TF-IDF par topic pour chaque modèle.

> **Ordre d'exécution** : après `03` et `04`, avant `05` si la comparaison doit informer le choix du modèle final.

Sorties : `comparison_grid_search.csv`, `comparison_bertopic_K{K}.csv`, `comparison_topics_K{K}.csv`, `embeddings_specter_cache.npy`, `umap_specter_cache.npy`.

---

### `04c_specter_explore.py` — Exploration qualitative de SPECTER à son optimum *(optionnel)*

Fit BERTopic avec SPECTER à K=14, optimum du rang agrégé SPECTER issu de `comparison_grid_search.csv`. Permet d'évaluer si cet optimum statistique produit des topics disciplinairement interprétables. Sur ce corpus, l'inspection qualitative révèle des clusters larges et hétérogènes (les trois premiers topics représentent 17,7 %, 13,2 % et 11,1 % du corpus et mélangent plusieurs thématiques distinctes), confirmant que l'avantage structurel de SPECTER sur un corpus académique ne se traduit pas en interprétabilité disciplinaire.

Le paramètre `K_SPECTER` peut être modifié en tête de script pour tester d'autres valeurs (K=15 et K=17 sont les candidats suivants selon les rangs agrégés). Requiert les caches SPECTER produits par `04b`.

Sorties : `specter_topics_K14.csv`.

---

### `05_bertopic_fit.py` — Fit BERTopic final et métriques avant fusion

Charge `best_n` depuis `best_n.json` et ajuste BERTopic avec Ward (`n_clusters=best_n`) substitué à HDBSCAN. Le modèle reçoit l'embedding model MPNet, un UMAP `n_components=5`, Ward comme modèle de clustering, et un CountVectorizer avec lemmes et bigrammes. `fit_transform` est appelé sur `docs` avec les embeddings pré-calculés ; `update_topics` est ensuite appelé sur `docs_ctfidf` pour que le c-TF-IDF reflète la normalisation partielle par lemmes.

Les métriques (Silhouette, CH, DB) sont calculées dans l'espace UMAP 5d, pas dans l'espace 768d — cohérence géométrique : c'est dans cet espace que Ward a opéré.

Sorties : `metrics_before_merge.csv`, `topic_coherence_before_merge.csv`, `document_topics_before_merge.csv`, `bertopic_model_before_merge/`, `topics_before_merge.npy`.

---

### `06_similarity_analysis.py` — Matrice de similarité inter-topics

Calcule la matrice de similarité cosinus entre les topic embeddings BERTopic (vecteurs moyens des clusters dans l'espace 768d). Les paires dépassant `SIMILARITY_THRESHOLD` (valeur par défaut, à ajuster dans la config) sont exportées comme candidates à la fusion. Une validation secondaire par similarité de Jaccard sur les top-20 termes c-TF-IDF est produite : cosinus élevé + Jaccard faible signale une similarité superficielle due au vocabulaire générique, et plaide contre la fusion.

Produit également la heatmap cosinus et la hiérarchie BERTopic avant fusion.

Sorties : `topic_similarity_matrix.csv`, `topic_similar_pairs.csv`, `topic_jaccard_pairs.csv`, `topic_similarity_comparison.csv`, `topic_similarity_heatmap.pdf/png`, `hierarchy_before_merge.html`.

---

### `07_merge_topics.py` — Fusion manuelle et recalcul c-TF-IDF

Applique la `MERGE_MAP` définie dans `config.py` : chaque clé (topic source) est remappée vers sa valeur (topic cible), qui agrège les documents des deux. `update_topics` est ensuite appelé **avec** `topics=list(topics_after)` — paramètre critique : sans lui, BERTopic recalculerait le c-TF-IDF sur les labels originaux, ignorant le remapping manuel.

Si `MERGE_MAP` est vide, aucune fusion n'est effectuée et les outputs reflètent l'état issu de `05`.

Sorties : `topic_coherence_after_merge.csv`, `document_topics_final.csv`, `bertopic_model_after_merge/`, `topics_after_merge.npy`, `n_after.json`.

---

### `08_coherence_cv.py` — Score de cohérence C_V (gensim)

Calcule le score de cohérence C_V (gensim) sur les topics thématiques après fusion, en excluant les topics de bruit éditorial (`NOISE_TOPIC_IDS` + topic 29) et les topics dont moins de 3 termes figurent dans le dictionnaire gensim. C_V mesure la cohésion sémantique des termes au sein de chaque topic à partir de co-occurrences dans le corpus (mais, au regard de la sparsité lexicale, C_V est instable et il s'agit davantage d'un indicateur complémentaire.)

Sorties : `coherence_after_merge.csv`.

---

### `09_metrics_final.py` — Métriques comparatives avant/après fusion

Relit `metrics_before_merge.csv` et recalcule Silhouette, CH et DB après fusion dans le même espace UMAP 5d, pour permettre la comparaison directe. Les métriques après fusion sont attendues stables ou légèrement dégradées si les fusions sont peu nombreuses et ciblées.

Sorties : `metrics_after_merge.csv`.

---

### `10_export_visualisations.py` — Visualisations finales et sauvegarde du modèle

Exporte le barchart et la hiérarchie du modèle final. Tente la sauvegarde en PDF via kaleido ; bascule automatiquement sur HTML si kaleido n'est pas disponible. Sauvegarde le modèle final sous `bertopic_ward_model_final/`.

Sorties : `barchart_final.pdf/html`, `hierarchy_final.pdf/html`, `bertopic_ward_model_final/`.

---

### `11_discriminant_terms.py` — Top 15 termes c-TF-IDF par topic

Lit directement les scores c-TF-IDF calculés par BERTopic via `get_topics()` sans re-vectorisation, garantissant la cohérence avec le modèle final. Produit un CSV à plat avec les 15 premiers termes de chaque topic, leur rang et leur score.

Sorties : `topic_top15_ctfidf.csv`.

---

## Note

Le choix de Ward à la place de HDBSCAN est motivé par un problème pratique : sur ce corpus, HDBSCAN produit un cluster dominant regroupant plus de 90 % des documents, incompatible avec une cartographie disciplinaire. Ward garantit l'assignation de tous les documents, un nombre de topics explicite et un résultat déterministe. La contrepartie est la nécessité de fixer K a priori — d'où la grid search multi-critères de l'étape `04`.

La lemmatisation différenciée (tokens originaux pour BERT, lemmes partiels pour c-TF-IDF) découle du fait que les transformers n'ont pas besoin de lemmatisation préalable, et la normalisation partielle améliore la discrimination lexicale du c-TF-IDF sans dégrader les embeddings.

---

## Dépendances

```
pip install numpy pandas bertopic sentence-transformers umap-learn scikit-learn matplotlib seaborn scipy gensim
```

Versions testées :

```
python                3.11
bertopic              0.16.x
sentence-transformers 2.x
umap-learn            0.5.x
scikit-learn          1.x
gensim                4.x
matplotlib            3.x
seaborn               0.13.x
```
