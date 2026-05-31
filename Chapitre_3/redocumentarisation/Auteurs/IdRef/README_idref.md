# Pipeline d'identification des auteurs via IdRef

Ce dossier regroupe les scripts utilisés pour enrichir la base de données locale avec les identifiants PPN d'IdRef (référentiel d'autorité personnes de l'Abes). La pipeline repose sur une comparaison par distance de Levenshtein entre les titres des publications associées à un auteur en base locale et les œuvres référencées pour chaque candidat dans IdRef. Les fichiers intermédiaires sont au format JSONL ou JSON. Les scripts couvrent trois grandes étapes : la collecte automatique des candidats, le triage des cas ambigus (un seul résultat dans IdRef mais pas de publications correspondantes trouvées) pour arbitrage humain, et l'injection des résultats en base.

Les scripts sont numérotés dans leur ordre d'exécution obligatoire. `01` doit impérativement précéder `02`, qui doit impérativement précéder `03`.

---

Fichiers d'entrée attendus :

| Fichier | Description |
|---|---|
| Table MySQL `auteur` | Auteurs dont la colonne `ppn_idref` est vide ou nulle |
| Table MySQL `reference` | Publications avec colonnes `title` et `secondary_title` |
| Table MySQL `ecriture` | Table de liaison auteur ↔ publication |

Fichiers de sortie principaux :

| Fichier | Produit par | Utilisé par |
|---|---|---|
| `idref_candidates.jsonl` | 01 | 02, 03 |
| `idref_to_review.json` | 02 | 03 |

---

## Description des scripts

### `01_auteurs_idref.py` — Collecte automatique des candidats IdRef

Charge depuis MySQL les auteurs sans `ppn_idref` ainsi que leurs titres locaux (via une jointure avec la table de liaison et la table des références). Pour chaque auteur, interroge l'API Solr d'IdRef avec le nom complet pour obtenir jusqu'à `MAX_CANDIDATES` PPN candidats. Pour chaque candidat, appelle l'endpoint `/services/biblio/{PPN}.json` et extrait les titres des œuvres référencées. Compare ensuite ces titres aux titres locaux par distance de Levenshtein normalisée : si le score dépasse le seuil `THRESHOLD` (0,8 par défaut), le PPN est validé et les candidats restants ne sont pas interrogés. Les résultats — matchs validés ou non — sont écrits ligne par ligne dans `idref_candidates.jsonl`, ce qui permet une reprise sans perte en cas d'interruption.

> Note méthodologique : le seuil de 0,8 a été fixé empiriquement. Un heuristique de containment (si l'un des deux titres contient l'autre et que tous deux font plus de dix caractères, le score est forcé à 1,0) traite les titres tronqués ou abrégés. Les cas à zéro candidat Solr (nom absent d'IdRef) et les cas à plusieurs candidats sans match sont conservés dans le JSONL pour mémoire et traçabilité.

Sorties : `idref_candidates.jsonl`.

---

### `02_idref_a_revoir_manuellement.py` — Triage des cas ambigus pour revue manuelle

Lit `idref_candidates.jsonl` et identifie les auteurs pour lesquels un seul candidat Solr a été trouvé mais qu'aucun match automatique n'a été validé. Ces cas sont les plus susceptibles d'être corrects — un seul homonyme dans IdRef — et les plus rapides à vérifier à la main. Pour chaque cas, le script recalcule le meilleur score Levenshtein et exporte un fichier JSON lisible, trié par score décroissant, avec les titres locaux et IdRef côte à côte pour faciliter la décision.

Le fichier produit (`idref_to_review.json`) est conçu pour être édité manuellement : le champ `"decision"` de chaque entrée doit être renseigné à `true` (PPN correct) ou `false` (PPN incorrect) avant de passer à l'étape suivante. Les entrées avec `"decision": null` sont ignorées par le script `03`.

Les cas à zéro candidat (absent d'IdRef) et à plusieurs candidats (ambiguïté non levée) sont exclus du fichier de revue et font l'objet d'un décompte dans la sortie console.

Sorties : `idref_to_review.json`.

---

### `03_inserer_idref_dans_bdd.py` — Injection des PPN en base MySQL

Met à jour la colonne `ppn_idref` de la table `auteur` à partir de deux sources possibles, détectées automatiquement selon l'extension du fichier passé en argument : le JSONL des matchs automatiques (`01`) ou le JSON des décisions manuelles (`02`). Un mode aperçu (par défaut) affiche les mises à jour prévues sans toucher à la base ; le flag `--commit` est requis pour appliquer les `UPDATE`. Seules les lignes dont `ppn_idref` est encore vide ou nul sont modifiées, ce qui rend le script idempotent.

Usage :
```bash
python3 03_inserer_idref_dans_bdd.py                               # aperçu depuis idref_candidates.jsonl
python3 03_inserer_idref_dans_bdd.py --input idref_to_review.json  # aperçu depuis le fichier de revue
python3 03_inserer_idref_dans_bdd.py --commit                      # applique les UPDATE
python3 03_inserer_idref_dans_bdd.py --input idref_to_review.json --commit
```

Sorties : mise à jour en base (aucun fichier produit).

---

## Note méthodologique

IdRef est principalement adapté aux auteurs francophones ou publiés dans le circuit documentaire français. Pour les auteurs d'autres nationalités, le taux d'échec est structurellement plus élevé, indépendamment du protocol -- d'où notre usage d'autres référentiels d'autorités documentés dans ce repo, dans la mesure du possible et de ce que le droit nous permet.

---

## Dépendances

```
pip install mysql-connector-python requests python-Levenshtein
```

Versions testées :

```
python                 3.11
mysql-connector-python 8.x
requests               2.x
python-Levenshtein     0.25
```

Une instance MySQL locale est requise pour les scripts `01` et `03`. Les scripts `01` et `02` interrogent les API publiques d'IdRef (`https://www.idref.fr`) ; une connexion internet est donc nécessaire pour `01`.

**Note** : le nom de la base de données diffère entre `01` (`test_programme`) et `03` (`references_biblio`). À harmoniser selon l'environnement cible avant exécution.
