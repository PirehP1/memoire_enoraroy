# Enrichissement des auteurs via Wikidata

Ce script interroge le Wikidata Query Service pour enrichir les entrées d'auteurs de la base locale avec des identifiants supplémentaires, le genre (P21), la nationalité (P27) et les langues d'expression (P1412). Il cible les auteurs disposant d'au moins un identifiant d'autorité connu : ORCID, VIAF, ISNI, IdRef, BNF, GND, Scopus, IEEE ou Google Scholar.

---

Fichiers d'entrée attendus : Auteurs avec au moins un identifiant d'autorité renseigné dans MySQL

Fichiers de sortie principaux :

| Fichier | Description |
|---|---|
| `wikidata_authors.jsonl` | Un objet JSON par auteur : QID, identifiants Wikidata, genre, nationalité, langues |
| `wikidata_checkpoint.json` | Dernier `id` traité, supprimé automatiquement à la fin d'un traitement complet |

---

## Description du script

### `wikidata_enrichissement_et_alignement_referentiels.py.` — Collecte et enrichissement via Wikidata

Charge depuis MySQL tous les auteurs dont au moins une colonne d'identifiant est renseignée. Pour chaque auteur, construit une requête SPARQL unique combinant en `UNION` tous ses identifiants disponibles, ce qui permet de trouver l'entité Wikidata correspondante en un seul aller-retour réseau. La même requête récupère simultanément, via des clauses `OPTIONAL` et `SERVICE wikibase:label`, l'ensemble des identifiants externes connus de l'entité ainsi que les labels de genre, nationalité et langues en français (avec repli sur l'anglais).

Les résultats sont écrits ligne par ligne dans `wikidata_authors.jsonl` et un checkpoint est mis à jour après chaque auteur, ce qui permet une reprise sans perte en cas d'interruption (Ctrl+C intercepté proprement). Un délai de courtoisie fixe (`REQUEST_DELAY = 2,0 s`) est appliqué après chaque requête SPARQL ; un backoff exponentiel prend le relais en cas de réponse 429.

> Note : il me semble qu'il est possible de faire des demandes par batch à Wikidata, ce qui n'a pas été implémenté ici.

---

## Format de sortie

Chaque ligne de `wikidata_authors.jsonl` est un objet JSON de la forme :

```json
{
  "id_bdd": 42,
  "nom_complet": "Dupont, Marie",
  "wikidata": {
    "wikidata_qid": "Q12345",
    "identifiants": {
      "orcid": {"valeur": "0000-0001-2345-6789", "propriete_wikidata": "P496"},
      "viaf":  {"valeur": "987654",              "propriete_wikidata": "P214"}
    },
    "genre":      {"label": "feminin",   "wikidata_qid": "Q6581072", "propriete_wikidata": "P21"},
    "nationalite":{"label": "Française", "wikidata_qid": "Q142",     "propriete_wikidata": "P27"},
    "langues_expression": {
      "valeurs": [{"label": "français", "wikidata_qid": "Q150"}],
      "propriete_wikidata": "P1412"
    },
    "identifiant_source": {"propriete_wikidata": "P496", "valeur": "0000-0001-2345-6789"}
  }
}
```

Le champ `"wikidata"` vaut `null` pour les auteurs introuvables dans Wikidata.

---

## Dépendances

```
pip install requests mysql-connector-python
```


Une instance MySQL locale est requise. Le script interroge le Wikidata Query Service public (`https://query.wikidata.org`) ; une adresse mail, même placeholder, est conseillée.

---

