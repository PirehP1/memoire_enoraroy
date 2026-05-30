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
