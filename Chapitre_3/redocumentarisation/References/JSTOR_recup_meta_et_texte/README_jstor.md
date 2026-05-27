# Correspondance des références bibliographiques avec JSTOR

Ce dossier regroupe les scripts utilisés pour redocumentariser ma base de données MySQL en la croisant avec les métadonnées JSTOR auxquelles j'ai accès via mon abonnement Paris 1. Ces métadonnées sont fournies sous forme d'un énorme fichier `.jsonl` de plus de 10Go, que j'ai découpé en fichiers jsonl de 300 000 lignes pour un traitement plus facile. Il ne s'agit donc pas de l'intégralité du catalogue JSTOR, mais uniquement du sous-ensemble correspondant à mes droits d'accès.

L'objectif est d'enrichir la table `reference` avec un `jstor_item_id` pour chaque référence identifiée, ce qui permettra ensuite de récupérer des métadonnées complémentaires ou de faire une demande à JSTOR pour le texte complet de la référence. La logique est identique à celle adoptée pour la déduplication : les scripts fonctionnent par étapes progressivement moins strictes quant à la correspondance.

> NOTE : Les seuils de similarité retenus (Levenshtein) sont indicatifs. Un seuil trop bas génère des faux positifs (deux ressources différentes associées à tort) ; un seuil trop haut laisse passer des correspondances réelles. Je recommande de commencer par les seuils les plus stricts et de les ajuster selon le taux de résultats obtenus sur vos données.

---

## Dépendances

```
pip install mysql-connector-python python-Levenshtein
```

---

## Architecture générale

Chaque étape (sauf la première) se décompose en deux scripts :

- un script  qui produit des paires candidates en filtrant les articles JSTOR selon un critère structurel (DOI, ISSN/ISBN, année, titre secondaire) — ces fichiers `.jsonl` intermédiaires peuvent être volumineux ;
- un script **`b`** qui valide ces paires par comparaison de titres (distance de Levenshtein) et produit le fichier `.json` final, trié par `ref_id`.

L'ensemble des fichiers de résultats est ensuite inséré par le script dédié.

```
01  → resultats_doi_jstor.json
02 + 02b → candidate_pairs.jsonl → resultats_isbn_jstor.json
03 + 03b → candidate_pairs_year.jsonl → resultats_annee_jstor.json
04 + 04b → candidate_pairs_titles.jsonl → resultats_titre_jstor.json
            ↓
     insertion_resultats_bdd.py  →  mise à jour MySQL
```

---

## Description des scripts

### `01_comparaison_doi_worldcat_jstor.py`

Croise les DOI présents dans la base MySQL (champ `doi` de la table `reference`) avec le champ `ithaka_doi` de chaque article JSTOR, et puisque c'est la méthode la plus fiable, aucune comparaison textuelle n'est nécessaire.

**Sortie :** `resultats_doi_jstor.json` — une entrée par référence ayant un DOI, avec `"trouve": true/false`, le `jstor_item_id` et l'URL JSTOR le cas échéant.

---

### `02_extraire_issn_isbn_commun_bdd_jstor.py`

Pour les références portant un ISSN ou ISBN (le champ `issn` peut contenir plusieurs valeurs séparées par des points-virgules), filtre les articles JSTOR dont les identifiants (`print_issn`, `online_issn`, `print_isbn`, `online_isbn`) correspondent. Les identifiants sont normalisés (suppression des tirets et espaces) avant comparaison.

**Sortie :** `candidate_pairs.jsonl` — paires (référence MySQL, article JSTOR) candidates, dédoublonnées par couple `(ref_id, jstor_item_id)`.

`02b_comparaison_titre.py` : Valide les paires de `candidate_pairs.jsonl` par comparaison des titres en testant 4 configurations (titre principal / titre secondaire), et retenant le meilleur score.

**Sortie :** `resultats_isbn_jstor.json`.

---

### `03_comparaison_annee.py`

Pour les références portant une année de publication, produit toutes les paires (référence, article JSTOR) partageant la même année. L'année JSTOR est extraite du champ `published_date` (format `AAAA-MM-JJ`). Ce critère seul étant très peu discriminant, le volume de paires candidates peut être important.

**Sortie :** `candidate_pairs_year.jsonl`.

`03b_match_titre_annee.py` : Valide les paires candidates par score combiné titre + titre secondaire. Cas particulier : si le titre principal est générique (`Introduction`, `Conclusion`, `Preface`, etc.), seul le titre secondaire est utilisé, avec un seuil plus strict.

**Sortie :** `resultats_annee_jstor.json`.

---

### `04_comparaison_titre_sec.py`

Traite uniquement les références sans DOI, sans ISSN/ISBN **et** sans année. Une comparaison exhaustive est effectuée entre le titre secondaire de chaque référence et le champ `is_part_of` de chaque article JSTOR et seules les paires dépassant un seuil de pré-filtrage de 0,75 sont retenues. ATTENTION ! Le traitement peut être particulièrement LONG puisqu'on compare tout le contenu textuel de JSTOR!!


**Sortie :** `candidate_pairs_titles.jsonl`.

`04b_match_titre_ex.py` : Valide les paires de `candidate_pairs_titles.jsonl` selon la même logique que `03b` (score combiné titre + titre secondaire, gestion des titres génériques). Affiche une progression toutes les 10 000 paires évaluées.

**Sortie :** `resultats_titre_jstor.json`.

---

### `insertion_resultats_bdd.py`

Lit les quatre fichiers de résultats dans l'ordre de priorité (DOI > ISSN/ISBN > année > titre) et retient, pour chaque `ref_id`, le premier `jstor_item_id` trouvé.

---
