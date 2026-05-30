# `bnf_match.py` — Appariement des auteurs avec les notices d'autorité de la BnF

## Description

Ce script réalise un appariement automatisé entre les auteurs stockés dans une base de données MySQL locale et les notices d'autorité de personnes physiques produites par la Bibliothèque nationale de France (BnF), distribuées au format ISO 2709 / UNIMARC à l'adresse [suivante](https://api.bnf.fr/fr/notices-dautorite-personnes-collectivites-oeuvres-lieux-noms-communs-de-bnf-catalogue-general). Je ne fournis pas les données ici, celles-ci étant très volumineuses et disponibles au téléchargement en ligne.

Il est aussi vivement conseillé de vérifier rapidement le fichier de résultats de match avant toute insertion en bases de données.

## Fonctionnement

Le script procède en trois temps :

1. **Chargement** des auteurs depuis la base MySQL, avec leurs titres de publications associés.
2. **Lecture**  des fichiers d'autorité BnF, notice par notice, afin de ne pas charger des fichiers potentiellement volumineux en mémoire.
3. **Appariement** par double critère : similarité du nom (distance de Levenshtein normalisée) et similarité d'au moins un titre commun (champ UNIMARC 810), permettant de distinguer les homonymes.

Un index inversé sur les tokens de noms réduit le nombre de comparaisons effectives. Les résultats sont écrits dans un fichier JSONL (`bnf_candidates.jsonl`), avec reprise possible en cas d'interruption.

## Fichier de sortie

`bnf_candidates.jsonl` — une ligne par auteur traité :

```json
{"author_id": 42, "name": "Dupont Jean", "match": {"bnf_id": "...", "bnf_name": "...", "score": 0.87, "title_local": "...", "title_bnf": "..."}}
{"author_id": 43, "name": "Smith John", "match": null}
```

## Dépendances

```
mysql-connector-python
python-Levenshtein
tqdm
```

Les fichiers d'autorité BnF (format ISO 2709) doivent être placés dans le dossier `data_bnf/`. Les paramètres de connexion MySQL et les seuils de validation sont configurables en tête de script.

## Limites et portée effective dans ce projet

L'usage de ce script dans le cadre de la présente recherche est resté marginal. La BnF constitue un référentiel centré sur les auteurs et éditions francophones, alors que notre corpus est majoritairement anglophone. Pour ces auteurs, la BnF dispose rarement d'une notice d'autorité complète, et plus rarement encore d'un champ 810 renseigné — condition nécessaire à la validation de l'appariement par les titres. Le taux de match effectif est donc structurellement limité aux auteurs francophones déjà largement couverts par IdRef.

Le script a néanmoins été conservé et documenté pour des raisons de traçabilité du protocole, et pourrait s'avérer plus utile dans un corpus centré sur la production francophone ou sur des auteurs ayant une production monographique significative.

> **Note technique.** Ce script a été largement rédigé avec l'assistance de LLM, notamment pour le parseur ISO 2709 maison. Des tentatives préalables avec la bibliothèque `pyunimarc` n'avaient pas abouti et n'ont pas été approfondies au regard de l'usage limité du script.

