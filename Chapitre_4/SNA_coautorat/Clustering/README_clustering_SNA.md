# Clustering de Leiden sur le graphe de co-autorat

**IMPORTANT** : je n'ai, me semble-t-il, pas expliqué dans mon mémoire la méthodologie employée pour le clustering. Par conséquent, pour compenser ce manque, je propose ici d'expliquer la méthode et de présenter les résultats bruts ; sans prétendre que cela remplace mon erreur.

> Les programmes ayant été réalisés par M. Lamassé, que je remercie tout particulièrement, je lui laisse le soin de les publier, exposant ici uniquement la méthodologie générale et les résultats.

L'objectif est d'identifier des sous-groupes cohésifs (clusters) au sein d'un réseau de co-autorat, c'est-à-dire des ensembles d'auteurs et de publications qui co-publient davantage entre eux qu'avec le reste du réseau. Ces clusters permettent de repérer des espaces disciplinaires, des collectifs de pratique, ou des configurations institutionnelles structurées (laboratoires, projets, instruments partagés).

## Le graphe d'entrée : un graphe biparti

Le réseau est représenté sous la forme d'un **graphe biparti**. Un graphe biparti est un graphe dont les nœuds sont répartis en **deux ensembles disjoints** — ici :

| Ensemble | Contenu |
|---|---|
| **A** | Les **auteurs** |
| **B** | Les **publications** |

---

## L'algorithme : Leiden

### Principe général

Le programme applique l'algorithme de Leiden, une amélioration de l'algorithme de Louvain pour la détection de communautés dans les grands graphes. Il procède en trois phases répétées itérativement :

1. Phase de déplacement local : chaque nœud est déplacé vers la communauté voisine qui maximise le plus le gain de modularité.
2. Phase de raffinement : les communautés sont subdivisées pour éviter les partitions sous-optimales, ce qui distingue Leiden de Louvain.
3. Phase d'agrégation : le graphe est réduit : chaque communauté devient une sorte de noeud.Un nouveau graphe est alors construit, sur lequel les étapes précédentes sont répétées jusqu'à ce qu'aucune amélioration supplémentaire de la fonction qualité ne soit possible

Le processus s'arrête lorsqu'aucun déplacement ne permet d'améliorer la partition.

### Avantages pour ce réseau

- Passe à l'échelle sur des graphes de grande taille (plusieurs milliers de nœuds et d'arêtes).
- Garantit que chaque communauté est **bien connectée** en interne (propriété absente de Louvain).
- Produit des résultats stables et reproductibles avec une graine aléatoire fixée.

---

## La fonction de qualité : modularité de Barber

La modularité standard (Newman & Girvan) est conçue pour les graphes unipartis. Appliquée directement à un graphe biparti, elle produirait des résultats inadaptés car elle ne distingue pas les deux types de noeuds.

Le programme utilise donc la **modularité de Barber** (Barber, 2007), une adaptation explicitement conçue pour les graphes bipartis :

    Q_B = (1/m) × Σ_ij [ B_ij − (k_i^A × k_j^B / m) ] × δ(c_i, c_j)

où :
- `m` est le nombre total d'arêtes (paires auteur–publication),
- `B_ij` vaut 1 s'il existe une arête entre le noeud i (auteur) et le noeud j (publication),
- `k_i^A` et `k_j^B` sont les degrés respectifs de l'auteur i et de la publication j,
- `δ(c_i, c_j)` vaut 1 si i et j appartiennent au même cluster.

En d'autres termes, la modularité de Barber compare le nombre d'arêtes observées entre les noeuds appartenant à une même communauté à ce qu'on attendrait dans un **modèle nul aléatoire biparti** (qui conserve les degrés de chaque noeud). Un Q_B élevé indique des clusters bien définis.

---


## Sorties du programme

### Attribution des nœuds aux clusters

Chaque auteur et chaque publication se voit attribuer un identifiant de cluster (entier, de 0 à n). Le cluster 0 est ici le plus gros en nombre de nœuds.

### Matrice d'adjacence réordonnée

Les nœuds sont réordonnés selon leur cluster d'appartenance, faisant apparaître une **structure diagonale par blocs**. Les blocs denses sur la diagonale indiquent des clusters où auteurs et publications co-publient intensément entre eux. Les points hors diagonale traduisent les ponts entre clusters (circulation inter-groupes).

---

## Interprétation de quelques clusters (LCC)

| Cluster | Caractéristiques observées |
|---|---|
| **0** | Le plus peuplé (> 700 auteurs). Quasi-exclusivement dédié aux **recensions**. Pratique individuelle, peu de liens de co-autorat internes. |
| **1, 2, 5, 7, 8** | Centrés sur la **génomique et l'ADN** (archéogénomique). |
| **3, 4, 6, 9** | Centrés sur la **dendrochronologie** et l'archéologie du climat / paléoclimatologie. |
| **10–12** | Autres sous-espaces des sciences naturelles. |

Les clusters 1 à 12 (hors cluster 0) représentent à eux seuls plus du quart des auteurs et des publications du réseau, pour seulement ~15 % des clusters (12 sur 79 au total). Cela confirme la concentration des pratiques de co-autorat dans les sciences naturelles.

---

