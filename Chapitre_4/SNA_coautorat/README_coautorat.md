# Analyse réseau de coautorat

Ce dossier regroupe les scripts utilisés pour l'analyse en réseau de co-autorat (Social Network Analysis, SNA) développée au chapitre 4 du mémoire. Les fichiers de nœuds/arêtes sont exportés au format CSV depuis MongoDB. Les scripts couvrent trois grandes étapes : la construction et le calcul des métriques de centralité, les analyses statistiques transversales, et les analyses temporelles sur réseau cumulatif.

Les scripts sont numérotés dans leur ordre d'exécution recommandé. Les étapes `01` et `02` sont des prérequis indispensables ; les étapes `02b` à `07` sont indépendantes entre elles et peuvent être lancées dans n'importe quel ordre une fois `02` terminé ; les étapes `08` à `10` forment une sous-pipeline temporelle où `08` doit impérativement précéder `09` et `10`.

---

Fichiers d'entrée attendus (à placer dans `Noeuds_et_aretes/`) :

| Fichier | Description |
|---|---|
| `nodes_all.csv` | Liste de tous les nœuds avec colonnes `Id` et `Type` (`author` / `publication`) |
| `edges_author_pub.csv` | Liste des arêtes bipartites avec colonnes `Source`, `Target`, `Year` |

Fichiers de sortie principaux (produits dans `output/`) :

| Fichier | Produit par | Utilisé par |
|---|---|---|
| `auteur_simple_nodes.csv` | 02 | 03, 06, 07, 09 |
| `pub_simple_nodes.csv` | 02 | 03, 05, 07 |
| `auteur_newman_nodes.csv` | 02 | 07 |
| `pub_newman_nodes.csv` | 02 | 07 |
| `temporal/result_temporal_nodes_simple.csv` | 08 | 09, 10 |
| `temporal/result_temporal_nodes_pub.csv` | 08 | 10 |

---

## Description des scripts

### `01_description_donnees.py` — Statistiques descriptives du réseau

Produit une vue d'ensemble du corpus avant toute analyse de réseau. À partir des fichiers CSV de nœuds et de la base MongoDB, le script reconstitue pour chaque auteur le nombre de nationalités renseignées et la présence d'un identifiant d'autorité (ISNI, VIAF, ORCID), et pour chaque publication la langue et l'année de parution. Les résultats sont exportés dans trois formats : JSON (données brutes), CSV (tableau de synthèse) et LaTeX (table prête à l'inclusion dans le mémoire). Un tableau des dix langues les plus représentées est également produit séparément.

Sorties : `result_descriptive_stats.json`, `result_descriptive_stats.csv`, `result_top_langues.csv`, `tex/descriptive_stats.tex`, `tex/top_langues.tex`.

---

### `02_calcul_metriques.py` — Construction du réseau et calcul des métriques de centralité

Script essentiel du workflow puisqu'il construit le graphe biparti auteur-publication à partir des CSV, puis produit quatre projections monopartites en appliquant deux schémas de pondération distincts.
- **Projection simple** : le poids d'un lien entre deux auteurs (ou deux publications) correspond au nombre de publications qu'ils partagent.
- **Projection de Newman** : le poids est calculé selon la formule Σ_p 1/(k_p − 1), où k_p désigne le nombre de co-auteurs de la publication p. Ce facteur pénalise les grandes collaborations collectives, jugées moins significatives qu'une collaboration duale, conformément à la proposition de Newman (2001).

Pour chacune des quatre projections, le script calcule les indicateurs globaux (densité, diamètre de la LCC, clustering moyen, degré moyen) et les indicateurs par nœud : degré binaire et pondéré, betweenness, PageRank, centralité de Katz (PageRank et Katz sont abandonnés par la suite mais ces scripts n'ont pas été modifiés en ce sens), centralité eigenvector, coefficient de clustering. Les résultats sont exportés en CSV, en GraphML (format Gephi) et en LaTeX.

Sorties : `auteur_simple_nodes.csv`, `auteur_newman_nodes.csv`, `pub_simple_nodes.csv`, `pub_newman_nodes.csv`, `result_coauthorship_simple.graphml`, `result_coauthorship_newman.graphml`, fichiers d'arêtes CSV, tableaux LaTeX.

---

### `02b_contingence_theme_appartenance_LCC.py` — Test du χ² thème / appartenance à la LCC

Ce script permet de voir si la distribution thématique des publications diffère significativement selon qu'elles appartiennent ou non à la composante connexe principale (LCC). Il reconstruit la LCC à partir du graphe biparti, récupère les topics assignés à chaque publication via MongoDB (champ `topic_analysis`), puis construit un tableau de contingence croisant topic et appartenance à la LCC.

Le test du χ² global est suivi d'un calcul des résidus ajustés pour chaque topic, ce qui permet d'identifier les thèmes sur-représentés ou sous-représentés dans la composante principale. Les topics dont l'effectif total est inférieur à 5 occurrences sont exclus de l'analyse.

Sorties : `khi2_topics_composante_principale.csv`.

---

### `03_gini_indicateurs_centralite.py` — Coefficient de Gini et courbes de Lorenz

Mesure l'inégalité de la distribution de chaque indicateur de centralité au sein du réseau, séparément pour les auteurs et pour les publications. Pour chaque métrique (degré, betweenness, PageRank, Katz, eigenvector, clustering), le script calcule le coefficient de Gini et trace la courbe de Lorenz correspondante. Seuls les nœuds avec une valeur strictement positive sont retenus, ce qui exclut les nœuds isolés dont la centralité nulle n'est pas informative. L'aire entre la courbe de Lorenz et la diagonale d'égalité est colorée pour faciliter la lecture.

Sorties : `img/lorenz_auteurs_<metrique>.png`, `img/lorenz_publications_<metrique>.png`.

---

### `04_boxplot_nb_coauteur_composante.py` — Distribution du nombre de co-auteurs par composante

Calcule, pour chaque auteur, le nombre de co-auteurs distincts avec lesquels il a collaboré (au moins une fois) dans le réseau biparti, puis compare cette distribution entre la composante connexe principale et l'ensemble des composantes secondaires.

Le calcul est effectué directement sur le graphe biparti : pour un auteur donné, ses co-auteurs sont les auteurs qui partagent avec lui au moins une publication commune (voisins de ses voisins dans le graphe biparti). La comparaison est visualisée sous forme de deux boxplots horizontaux superposés sur une échelle logarithmique, accompagnés des statistiques descriptives (médiane, Q1, Q3, maximum).

Sorties : `boxplots_coauteurs.png`, `boxplots_coauteurs.svg`.

---

### `05_kruskal_langue_centralite.py` — Test de Kruskal-Wallis langue / centralité

Teste si la langue de publication constitue un facteur différenciant significatif des indicateurs de centralité. Pour chaque métrique disponible, un test de Kruskal-Wallis est effectué sur les groupes formés par les langues représentées par au moins 5 publications. Les langues non renseignées (`inconnu`, `unknown`) sont exclues de l'analyse. La langue est récupérée depuis MongoDB (champ `language_name`) plutôt que depuis le fichier CSV, afin de disposer de la valeur la plus complète et la plus propre.

Sorties : `kruskal_langue_centralite.csv`.

---

### `06_boxplot_nationalite_centralite.py` — Distribution de la centralité par nationalité

Visualise la distribution d'un indicateur de centralité (configurable via la constante `METRIC` en tête de script) pour les huit nationalités les plus représentées dans le réseau d'auteurs. Les nationalités sont obtenues depuis MongoDB (champ `nationalites`) et fusionnées avec les métriques de centralité calculées par le script `02`.

**Note méthodologique** : les auteurs ayant plusieurs nationalités sont dupliqués — une ligne par pays après la jointure. Chaque nationalité reçoit le score de centralité de l'auteur concerné. Ce choix gonfle légèrement les effectifs des pays les plus représentés mais permet une lecture par nationalité plutôt que par auteur. Cette convention est signalée dans le titre du graphe. Les boxplots sont triés par médiane croissante et affichés sur une échelle logarithmique ; les moyennes sont figurées par un losange orange.

Sorties : `boxplot_<metrique>_nationalite.png`.

---

### `07_correlation_indicateur_centralite.py` — Matrices de corrélation de Spearman

Calcule les corrélations de Spearman entre les différents indicateurs de centralité, séparément pour les auteurs (projections simple et Newman) et pour les publications (projections simple et Newman). Dans chaque cas, l'analyse est restreinte aux nœuds appartenant à la LCC, identifiée par reconstruction du graphe biparti.

Les corrélations sont présentées sous forme de heatmaps (triangle inférieur uniquement), où chaque cellule affiche le coefficient ρ et la valeur de p brute. La palette divergente (bleu pour les corrélations positives, rouge pour les corrélations négatives) est centrée sur 0. Les matrices sont également exportées en LaTeX.

Sorties : `img/heatmap_corr_auteurs_simple.png`, `img/heatmap_corr_auteurs_newman.png`, `img/heatmap_corr_publications_simple.png`, `img/heatmap_corr_publications_newman.png`, fichiers `.tex` associés.

---

### `08_metriques_centralite_temporelles.py` — Métriques de centralité sur réseau cumulatif

Script de la sous-pipeline temporelle. Il reconstruit les réseaux de manière cumulative, année par année, de 1975 à 2025, en mettant à jour les graphes : seules les nouvelles publications de chaque année sont ajoutées, sans reconstruction complète depuis le graphe biparti, réduisant le temps de calcul.

Trois réseaux sont maintenus en parallèle : la projection auteur-auteur simple (poids = publications partagées), la projection auteur-auteur de Newman (poids = Σ 1/(k−1)), et le réseau publication-publication (poids = auteurs partagés). Pour chaque année et chaque réseau, les indicateurs globaux (densité, taille de la LCC, diamètre, clustering moyen) et les métriques par nœud (degré, closeness, betweenness topologique exacte, eigenvector) sont calculés et exportés.

**Note méthodologique** : PageRank et Katz ont été écartés de l'analyse temporelle. La betweenness est calculée de façon exacte.

Sorties : `temporal/result_temporal_global.csv`, `temporal/result_temporal_global_pivot.csv`, `temporal/result_temporal_nodes.csv`, `temporal/result_temporal_nodes_simple.csv`, `temporal/result_temporal_nodes_newman.csv`, `temporal/result_temporal_nodes_pub.csv`, `tex/temporal_global_pivot.tex`.

---

### `09_correlation_annee_entree_LCC_et_centralite.py` — Corrélation Spearman ancienneté / centralité

Teste si l'ancienneté dans la composante connexe principale — mesurée par l'année d'entrée dans la LCC — est corrélée aux indicateurs de centralité calculés en synchronie (snapshot final). L'analyse distingue deux populations : la population complète (Run A) et le top 1 % des auteurs les plus centraux pour chaque indicateur (Run B).

L'année d'entrée dans la LCC est reconstituée de façon cumulative : à chaque année t, on identifie quels auteurs intègrent pour la première fois la composante principale. La LCC est considérée comme stable à partir de 2000, année à partir de laquelle elle dépasse 200 nœuds — les auteurs présents dès cette première LCC stable reçoivent tous l'année 2000 comme année d'entrée.

Sorties : `spearman_simple/dataset.csv`, `spearman_simple/resultats_spearman.csv`, `spearman_simple/scatter_spearman.png`.

---

### `10_gini_temporel.py` — Évolution du coefficient de Gini sur réseau cumulatif

Calcule l'évolution du coefficient de Gini pour les indicateurs de centralité au fil du temps, à partir des fichiers produits par `08`. Pour chaque année, la LCC est reconstruite depuis les arêtes cumulées, et le Gini est calculé sur les valeurs des nœuds présents dans cette LCC — ce qui garantit que l'évolution observée reflète la structure du réseau principal plutôt que les fluctuations des composantes isolées.

Les résultats sont visualisés sous forme de courbes temporelles (une par indicateur) superposées à des barres grises représentant la taille de la LCC.

Sorties : `img/gini_evolution_auteurs.png`, `img/gini_evolution_publications.png`, `gini_temporel_auteurs.csv`, `gini_temporel_publications.csv`.

---

## Notes méthodologiques

Ces scripts ont été développés au fur et à mesure de l'avancement de l'analyse et ne constituent pas nécessairement un workflow à suivre.

Si le réseau modélisé est bien plus vaste que la composante connexe principale, ma question portait principalement sur le coautorat structuré -- d'où le fait que je n'ai analysé que celle ci.

Les deux schémas de projection (simple et Newman) sont maintenus en parallèle, mais j'admet davantage utiliser la projection simple dans le mémoire. Le but d'avoir tenté les deux était aussi pédagogique, pour me faire mieux saisir leurs différences.

Par ailleurs, l'usage de LLM a été, pour ces scripts, davantage mobilisé que pour le reste de mon travail. Si la logique analytique — choix des indicateurs, seuils, conventions de traitement — reflète des décisions prises en connaissance de cause au fil de l'analyse, certains détails d'implémentation (gestion des structures de données, optimisations algorithmiques, syntaxe NetworkX) ont été délégués sans pour autant que je parvienne à saisir tous les détails. Ces scripts sont donc à considérer comme des outils de recherche reproductibles dans le cadre de ce mémoire, et non comme du code de production audité.

---

## Dépendances

```
pip install pandas numpy networkx scipy matplotlib seaborn pymongo
```

Versions testées :

```
python        3.11
pandas        2.2
numpy         1.26
networkx      3.3
scipy         1.13
matplotlib    3.9
seaborn       0.13
pymongo       4.7
```
Une instance MongoDB locale est requise pour les scripts `01`, `02b`, `05` et `06`, qui interrogent les collections `references` et `authors` de la base `references_biblio_mongo`.


---
