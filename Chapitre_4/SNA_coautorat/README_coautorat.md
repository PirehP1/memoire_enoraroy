# Analyse réseau de coautorat

Ce dossier regroupe les scripts utilisés pour l'analyse en réseau de co-autorat (Social Network Analysis, SNA) développée au chapitre 4 du mémoire. Les fichiers de nœuds/arêtes sont exportés au format CSV depuis MongoDB. Les scripts couvrent trois grandes étapes : la construction et le calcul des métriques de centralité, les analyses statistiques transversales, et les analyses temporelles sur réseau cumulatif.

Les scripts sont numérotés dans leur ordre d'exécution recommandé. Les étapes 01 et 02 sont des prérequis ; les étapes 03 à 07 sont indépendantes entre elles et peuvent être lancées dans n'importe quel ordre une fois 02 terminé ; les étapes 08 à 10 forment une sous-pipeline temporelle où 08 doit précéder 09 et 10 ; l'étape 11 est indépendante.

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

---
