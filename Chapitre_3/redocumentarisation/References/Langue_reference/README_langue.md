# Détection automatique de langue pour références bibliographiques

Ce dossier contient les scripts utilisés pour enrichir les publications avec la langue. Si le premier script, avec Crossref, peut aussi aller dans le dossier dédié, je tenais à le mettre ici comme part d'un pipeline indépendant de traitement.
Les scripts 01 à 03 produisent des fichiers JSON intermédiaires ; chaque étape n'opère que sur les références dont la langue n'a pas été détéctée par les précédentes. Le script 04 met à jour la base.

---

```
Base MySQL
    │
    ▼
01_detect_langue_crossref.py  ──►  resultats_01.json
    │ (DOI sans résultat CrossRef)
    ▼
02_detect_langue_doi_page.py                     ──►  resultats_02.json
    │ (sans DOI, ou toujours non résolus)
    ▼
03_titre_langue_spacy.py            ──►  resultats_03.json
    │
    ▼
04_insertion_langue_bdd.py    ──►  Base MySQL (language, source_lang)
```

| Script | Méthode | Entrée | Sortie |
|--------|---------|--------|--------|
| `01_detect_langue_crossref.py` | API CrossRef | MySQL | `resultats_01.json` |
| `02_detect_langue_doi_page.py` | Meta HTML + spaCy sur page | MySQL + `resultats_01.json` | `resultats_02.json` |
| `03_titre_langue_spacy.py` | spaCy sur les titres | MySQL + `resultats_01.json` + `resultats_02.json` | `resultats_03.json` |
| `04_insertion_langue_bdd.py` | Fusion et import en base | `resultats_01.json` + `resultats_02.json` + `resultats_03.json` | MySQL |

---

## Description des scripts

### Script 01 — API CrossRef

Interroge `https://api.crossref.org/works/{doi}` pour chaque référence possédant un DOI, avec un délai de 1s entre chaque requête.

**Sortie** : uniquement les références pour lesquelles CrossRef retourne un code de langue reconnu.

---

### Script 02 — Page web du DOI

Pour les DOI non résolus par le script 01. Suit la redirection `doi.org → éditeur` et applique le pipeline d'extraction suivant :

1. `<meta name="DC.language">` (Dublin Core)
2. `<meta name="citation_language">` (Highwire / Google Scholar)
3. `<meta name="language">`
4. `<html lang="...">`
5. spaCy sur le corps de la page, dans le cas où aucune balise meta n'est présente

Un fallback avec SSL désactivé est tenté automatiquement en cas d'erreur de certificat. Toutefois, il faut noter que certains sites chargent leur contenu en JavaScript ; le scraping HTML statique du script 02 échoue dans ces cas. Aussi, cette étape signifie qu'on présuppose que le site de l'éditeur est potentiellement dans la même langue).

> Après coup, ce n'est sans doute pas tout à fait pertinent et il faudrait sans doute passer directement du 01 au 03. En tous cas, si c'était à refaire, je ne crois pas recommencer ce second script.

**Sortie** : toutes les références traitées, y compris les échecs (`langue: "none"`).

> **Note** : le script 03 exclut uniquement les entrées effectivement résolues (langue non vide, non `"none"`) — les échecs du script 02 sont bien renvoyés à l'étape suivante.

---

### Script 03 — Analyse des titres par spaCy

Pour les références sans DOI ou non résolues aux étapes précédentes, ce script applique spaCy et langdetect sur le titre principal, puis sur le titre secondaire (revue ou ouvrage hôte) si le premier échoue. Le résultat est retenu uniquement si le score de confiance est ≥ 0,7. Les titres de moins de 9 caractères (la moyenne de longueur des mots dans les titres étant autour d'une dizaine de caractères, donc cela signifie un titre de un seul mot, plutôt court) et les titres génériques (`introduction`, `abstract`, `bibliography`, etc.) sont ignorés.

---

### Script 04 — Import en base

Fusionne les trois fichiers JSON en appliquant la priorité 01 > 02 > 03 : en cas de doublon, la source la plus fiable prime et ne peut être écrasée. Les entrées `langue = 'none'` ou vides sont ignorées, et le script met à jour les champs `language` et `source_lang` de la table `reference`.

Les valeurs `source_langue` des JSON sont normalisées avant insertion :

| Valeur JSON | Valeur en base |
|---|---|
| `crossref_api` | `crossref` |
| `html_meta` | `doi_webpage` |
| `spacy_page_content` | `doi_webpage` |
| `spacy` | `spacy` |

> **Attention** : en l'absence de rollback explicite, une interruption en cours d'exécution peut laisser la base dans un état partiel. Prévoir une sauvegarde avant le premier import.

---

## Format de sortie (JSON intermédiaires)

Chaque fichier JSON est une liste d'objets :

```json
[
  {
    "id": 1042,
    "langue": "fr",
    "source_langue": "crossref_api"
  }
]
```

Les valeurs possibles de `source_langue` :

| Valeur | Script | Signification |
|---|---|---|
| `crossref_api` | 01 | Langue fournie par l'API CrossRef |
| `html_meta` | 02 | Balise meta de la page éditeur |
| `spacy_page_content` | 02 | spaCy sur le corps de page |
| `spacy` | 03 | spaCy sur le titre principal ou secondaire |
| `no_detection` | 02 | Aucune méthode n'a abouti (pour l'instant) |

---

## Langues reconnues

### Périmètre retenu

Le pipeline ne reconnaît pas l'intégralité des codes ISO 639-1 existants (voir ci dessous). Si cela aurait été possible, je présuppose que le corpus ne nécessite pas davantage, puisque les grandes bases bibliographiques indexent peu les langues rares. Pour ne pas risquer des valeurs aberrantes avec des langues rares, j'ai préféré laisser tel quel et arbitrer en cas de langue en dehors de ces codes.

### Codes reconnus (34 langues, communs aux trois scripts)

`ar` `bg` `ca` `cs` `da` `de` `el` `en` `es` `et` `fi` `fr` `hr` `hu` `id` `it` `ja` `ko` `lt` `lv` `nl` `no` `pl` `pt` `ro` `ru` `sk` `sl` `sv` `th` `tr` `uk` `vi` `zh`

Les références dont la langue détectée ne figure pas dans cet ensemble ne sont pas enregistrées et passent en révision manuelle.

---

## Prérequis

### Python

Python ≥ 3.10 (pour la syntaxe `str | None`).

### Dépendances

```bash
pip install mysql-connector-python requests spacy spacy-language-detection langdetect
python -m spacy download en_core_web_sm
```

---
