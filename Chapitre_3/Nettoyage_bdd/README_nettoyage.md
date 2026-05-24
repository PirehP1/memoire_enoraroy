# Scripts de nettoyage — Base de données bibliographique

## Présentation

Ce dossier regroupe les scripts Python développés pour le nettoyage et la normalisation des données bibliographiques importées dans la base MySQL (et non MongoDB! puisque le nettoyage a été fait alors que nous étions encore dans le modèle relationnel).

Les données brutes, extraites depuis WorldCat, présentaient des artefacts : entités HTML résiduelles, balises non nettoyées, DOI insérés dans les champs texte, noms d'auteurs fusionnés ou mal encodés. Les scripts ci-dessous ont été conçus pour traiter ces anomalies de façon ciblée, traçable et reproductible.


## Organisation des scripts

Les scripts sont divisés en deux familles selon la table concernée : **`authors`** (noms d'auteurs) et **`reference`** (notices bibliographiques). Chaque script est autonome, documenté et, lorsque pertinent, propose une étape de prévisualisation avant toute modification de la base.

---

### Nettoyage de la table `authors`

#### `nettoyage_auteur_bdd.py`
Nettoyage général du champ `NomComplet` dans la table `authors`. Traite trois types d'anomalies :
- suppression des parenthèses englobantes (ex : `(Dupont, Jean)` = `Dupont, Jean`) ;
- suppression des astérisques (ex : `Dupont*, Jean` =`Dupont, Jean`) ;
- extraction des identifiants ORCID concaténés au nom dans une colonne dédiée (créée si absente).

Propose une prévisualisation avant application.

#### `nettoyage_auteur_esperluette.py`
Traite les entrées auteurs dont le champ `NomComplet` contient une esperluette (`&` ou `&amp;`), signalant plusieurs auteurs fusionnés en une seule ligne. Pour chaque entrée ciblée :
- découpe la chaîne en auteurs individuels ;
- crée les nouvelles entrées dans `authors` (ou retrouve les entrées existantes) ;
- transfère les liens de la table `ecriture` vers chaque nouvel auteur ;
- désactive l'entrée d'origine en la marquant comme ambiguë (`ambigu = 2`).

Les IDs à traiter sont définis manuellement dans la constante `TARGET_IDS`.
La notation de `ambigu` permet de ne pas supprimer de suite l'auteur, puisque nous ne savions pas encore s'il était pertinent de conserver les auteurs n'étant reliés à aucune référence (et permettait aussi de revenir en cas d'erreur). Au final, nous avons supprimé les auteurs qui n'étaient liés à aucune référence.

#### `nettoyage_auteur_html.py`
Décode les entités HTML résiduelles dans les champs `NomComplet`, `Nom` et `Prenom` pour une liste d'IDs ciblés. Gère :
- les entités nommées (`&aring;`, `&ouml;`…) ;
- les entités numériques décimales et hexadécimales (`&#237;`, `&#x11f;`…) ;
- les entités tronquées sans point-virgule final.

Applique une normalisation Unicode NFC après décodage.

---

### Nettoyage de la table `reference`

#### `nettoyage_reference_HTML.py`
Nettoie les champs `title` et `secondary_title` de la table `reference`. Supprime :
- les balises HTML résiduelles (`<b>`, `<i>`, `<sup>`, `<em>`, `<span>`…) ;
- les entités HTML (`&amp;`, `&lt;`…) ;
- les apostrophes doublées (`''` = `'`) ;
- les espaces multiples.

Propose une prévisualisation avant application.

#### `nettoyage_reference_artefact_titre.py`
Supprime les artefacts de début de titre introduits lors de l'import : points initiaux (`. Titre`), deux-points initiaux (`: Titre`), et crochets ouvrants (`[Titre]`), en reconstituant un titre propre.

#### `nettoyage_reference_doi.py`
Détecte et extrait les DOI insérés dans les champs `title` et `secondary_title`, selon plusieurs formats courants (`doi:`, `info:doi/`, URL `/doi/`…). Pour chaque DOI trouvé :
- extrait la valeur dans un fichier JSON intermédiaire (`doi_extracted_from_titles.json`) ;
- nettoie le champ source en supprimant le DOI et ses préfixes.

Propose une prévisualisation avant application.

#### `insertion_doi_nettoye.py`
Lit le fichier JSON produit par `nettoyage_reference_doi.py` et insère les DOI extraits dans la colonne `doi` de la table `reference`, uniquement pour les enregistrements dont ce champ est vide ou nul. Propose une prévisualisation avant insertion.

---

## Prérequis

- Python 3.10+
- Bibliothèque `mysql-connector-python`

```bash
pip install mysql-connector-python
```

La configuration de connexion à la base (`host`, `user`, `password`, `database`) est définie dans la constante `DB_CONFIG` de chaque script et doit être adaptée à l'environnement local avant exécution.

---

## Notes méthodologiques

Ces scripts ont été développés de manière incrémentale, au fur et à mesure que nous avons repéré des anomalies présentes dans les données importées. Ils ne constituent pas un pipeline de nettoyage universel, mais des interventions ciblées répondant à des problèmes documentés. Chaque script conserve une trace temporelle des modifications effectuées via le champ `date_modified` de la base.
