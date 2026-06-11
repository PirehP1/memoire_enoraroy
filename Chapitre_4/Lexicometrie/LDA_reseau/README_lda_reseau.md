# Analyse LDA × réseau

Ce dossier regroupe les scripts Python utilisés pour l'analyse croisée entre le modèle thématique LDA et la structure du réseau biparti auteurs-publications. Les données du réseau sont lues depuis des csv ; les données LDA sont lues depuis le dossier parent (`../output/`). Les trois scripts sont indépendants les uns des autres et peuvent être lancés dans n'importe quel ordre. La numérotation reflète la progression analytique : appariement des topics au réseau (`01`), test de sur/sous-représentation des topics par rapport au corpus propre (`02`), test de différence de centralité par topic (`03`).

**Prérequis** : le script `07_LDA_k.py` doit avoir été exécuté au préalable ; il produit `../output/topic_modelling/gamma_df.csv`, utilisé par les trois scripts.

---

Fichiers d'entrée :

| Fichier | Champs utilisés | Consommé par |
|---|---|---|
| `data/edges_author_pub.csv` | `Source`, `Target` | 01, 02, 03 |
| `data/nodes_all.csv` | `Id`, `Type`, `Label`, `year`, `label_thema` | 01, 02 |
| `data/metriques_reseau_bip.csv` | `Id`, `type`, indicateurs de centralité | 03 |
| `../output/corpus_propre/corpus_propre.json` | `document.doc_id` | 01, 02, 03 |
| `../output/topic_modelling/gamma_df.csv` | colonnes topics (gamma par document) | 01, 02, 03 |

Fichiers de sortie principaux :

| Fichier | Produit par |
|---|---|
| `output/publications_ccp_topics_lda.csv` | 01 |
| `output/publications_autres_cc_topics_lda.csv` | 01 |
| `output/contingence_T1_majority.csv`, `output/contingence_T1_threshold.csv` | 02 |
| `output/contingence_T2_majority.csv`, `output/contingence_T2_threshold.csv` | 02 |
| `output/residus_T1_majority.csv`, `output/residus_T2_majority.csv`, … | 02 |
| `output/contrib_T1_majority.csv`, `output/contrib_T2_majority.csv`, … | 02 |
| `output/heatmap_T1_majority.png`, `output/heatmap_T2_majority.png`, … | 02 |
| `output/recapitulatif_khi2.csv`, `output/rapport_statistiques.txt` | 02 |
| `output/kruskal/kruskal_summary.csv` | 03 |
| `output/kruskal/heatmap_kruskal_synthese.png` | 03 |
| `output/kruskal/rapport_kruskal.txt` | 03 |

---

## Description des scripts

### `01_associer_topics_reseau.py` — Appariement corpus propre × réseau × topics LDA

À partir des arêtes et nœuds exportés depuis Gephi, le script reconstruit le graphe et identifie ses composantes connexes. La composante connexe principale (CCP) est séparée des composantes secondaires. Chaque publication présente à la fois dans le corpus propre (fulltext disponible) et dans le réseau se voit associer son ou ses topics LDA dominants depuis les probabilités gamma : un topic est retenu si sa valeur gamma est supérieure ou égale au seuil `GAMMA_THRESHOLD` (par défaut `0.15`) ; si aucun topic n'atteint ce seuil, le topic de valeur maximale est retenu. Deux fichiers CSV sont exportés, l'un pour les publications de la CCP, l'autre pour les publications des composantes secondaires.

Sorties : `output/publications_ccp_topics_lda.csv`, `output/publications_autres_cc_topics_lda.csv`.

---

### `02_contingence_lda_reseau.py` — Sur/sous-représentation des topics dans le réseau (χ²)

Construit deux tableaux de contingence topics × appartenance au réseau, testés par un χ² d'indépendance, avec calcul du V de Cramér et des résidus standardisés de Pearson par cellule :

- **T1** — corpus propre complet × réseau (CCP + composantes secondaires) : teste si certains topics sont sur- ou sous-représentés parmi les publications présentes dans le réseau.
- **T2** — CCP × composantes secondaires (publications dans le réseau uniquement) : teste si la distribution des topics diffère entre la composante principale et les composantes secondaires.

Chaque tableau est produit selon deux modes d'attribution des topics :

- `majority` : un seul topic par publication (argmax de gamma) ;
- `threshold` : plusieurs topics si gamma ≥ `GAMMA_THRESHOLD` (par défaut `0.15`) ; si aucun n'atteint le seuil, le topic maximal est retenu.

Sorties : `contingence_T1/T2_majority/threshold.csv`, `residus_T1/T2_majority/threshold.csv`, `contrib_T1/T2_majority/threshold.csv`, `heatmap_T1/T2_majority/threshold.png`, `recapitulatif_khi2.csv`, `rapport_statistiques.txt` (tous dans `output/`).

---

### `03_kruskal_centralite.py` — Kruskal-Wallis : topic LDA × indicateurs de centralité

Pour chaque indicateur de centralité et chaque sous-corpus (réseau entier / CCP seule), le script teste si les distributions diffèrent selon le topic LDA dominant. Le test de Kruskal-Wallis est utilisé :

- H₀ : les distributions de centralité sont identiques entre tous les topics.
- H₁ : au moins un topic présente une distribution différente.

La taille d'effet est mesurée par ε² = H / ((n²−1) / (n+1)), avec les seuils suivants : ε² ≥ 0,01 (petit), ≥ 0,06 (moyen), ≥ 0,14 (grand). Les indicateurs testés sont : `degree`, `weighted degree`, `betweenesscentrality`, `eigencentrality`, `closnesscentrality`, `harmonicclosnesscentrality`. Une heatmap synthétique présente les p-values (−log₁₀) et les tailles d'effet ε² pour l'ensemble des tests.

Sorties : `output/kruskal/kruskal_summary.csv`, `output/kruskal/heatmap_kruskal_synthese.png`, `output/kruskal/rapport_kruskal.txt`.

---

## Notes

Le paramètre `GAMMA_THRESHOLD` (par défaut `0.15`) est défini dans la section `CONFIGURATION` de chaque script. Il est utilisé dans `01` pour l'attribution des topics dominants et dans `02` pour le mode `threshold` ; il n'intervient pas dans `03`, qui recourt exclusivement à l'argmax de gamma.

Les publications dont l'identifiant est absent du corpus propre ou de `gamma_df.csv` sont signalées dans les sorties CSV de `01` par les valeurs `"index_introuvable"` ou `"absent_de_gamma"` ; elles sont filtrées dans `02` (contribution nulle au tableau de contingence) et dans `03` (exclusion des lignes à `topic_lda` nul).

Dans `03`, les colonnes de centralité listées dans `CENTRALITY_COLS` qui sont absentes du fichier `metriques_reseau_bip.csv` sont ignorées sans erreur ; seules les colonnes effectivement présentes dans le CSV sont testées.

---

## Dépendances

```
pip install pandas networkx numpy matplotlib seaborn scipy
```

Les bibliothèques `numpy`, `matplotlib`, `seaborn` et `scipy` sont requises pour `02` et `03` uniquement ; `01` n'utilise que `pandas` et `networkx`.
