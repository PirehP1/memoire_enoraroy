## Fichiers produits

### Indicateurs globaux

`result_temporal_global.csv`

Une ligne correspond à un réseau donné pour une année donnée.

Variables :

* `year` : année du réseau cumulatif ;
* `reseau` : type de réseau (`simple`, `newman`, `pub`) ;
* `n_noeuds` : nombre de nœuds ;
* `n_liens` : nombre d'arêtes ;
* `densite` : densité du réseau ;
* `composantes` : nombre de composantes connexes ;
* `taille_lcc` : taille de la plus grande composante connexe ;
* `pct_lcc` : part des nœuds appartenant à la plus grande composante connexe ;
* `diametre_lcc` : diamètre de la plus grande composante connexe ;
* `clustering_moyen` : coefficient de clustering moyen ;
* `degre_moyen` : degré moyen.

### Tableau pivot

`result_temporal_global_pivot.csv`

Version réorganisée des indicateurs globaux avec une ligne par année et une colonne par couple (réseau, indicateur).

---

## Indicateurs par nœud

`result_temporal_nodes.csv` : Une ligne correspond à un nœud pour une année et un réseau donnés.

Variables :

* `id` : identifiant du nœud ;
* `year` : année du réseau cumulatif ;
* `reseau` : type de réseau ;
* `degree` : degré du nœud ;
* `closeness` : centralité de proximité ;
* `betweenness` : centralité d'intermédiarité ;
* `eigenvector` : centralité vecteur propre.

Des fichiers séparés sont également produits pour chaque réseau :

* `result_temporal_nodes_simple.csv`
* `result_temporal_nodes_newman.csv`
* `result_temporal_nodes_pub.csv`


