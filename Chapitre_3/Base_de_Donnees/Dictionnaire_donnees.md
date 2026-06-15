# Dictionnaire des données

Base de données **`references_biblio_mongo`** — deux collections MongoDB documentant l'espace de publication autour du concept de « barbare ».

Tous les champs listés ci-dessous représentent le *maximum observé* : un document donné peut n'en posséder qu'un sous-ensemble. Les champs marqués **non** dans la colonne *Optionnel* sont présents dans la quasi-totalité des documents.

> **Note légale** : le champ `ris_raw` de la collection `references` contient les données brutes exportées depuis Worldcat. Pour des raisons de propriété intellectuelle, ce champ n'est **pas inclus** dans la version distribuée de la base. De même, les numéros OCLC ont été retirés.

---

## Collection `references`

Chaque document représente une publication scientifique collectée via Worldcat.

### Champs de premier niveau

| Champ | Type | Optionnel | Description |
|---|---|---|---|
| `_id` | ObjectId | non | Identifiant unique MongoDB |
| `idmysql` | int | non | Identifiant hérité de la modélisation relationnelle initiale |
| `title` | string | non | Titre de la publication |
| `year` | int | oui | Année de publication |
| `type_of_reference` | string | oui | Type RIS du document (`JOUR`, `EJOUR`, `BOOK`…) |
| `language` | string | oui | Langue |
| `language_iso` | string | oui | Code ISO 639-1 (`en`, `fr`…) |
| `language_name` | string | oui | Nom normalisé de la langue en français |
| `language_qid` | string | oui | QID Wikidata de la langue (ex. `Q1860` pour l'anglais) |
| `issn` | string | oui | ISSN de la revue (plusieurs valeurs séparées par `;`) |
| `secondary_title` | string | oui | Titre de la revue ou de l'ouvrage hôte |
| `start_page` | string | oui | Mal nommé, représente les pages (intervalle possible, ex. `43-57`) |
| `volume` | string | oui | Volume |
| `number` | string | oui | Numéro |
| `publisher` | string | oui | Éditeur |
| `name_of_database` | string | oui | Base de données source dans Worldcat |
| `doi` | string | oui | Digital Object Identifier |
| `link` | string | oui | URL Worldcat de la notice |
| `abstract` | string | oui | Résumé de la publication |
| `fulltext` | boolean | oui | Indique si le texte intégral a été récupéré |
| `is_review` | boolean | oui | Indique si la publication est une recension (non fait systématiquement) |
| `nb_pages` | int | oui | Nombre de pages calculé |
| `nb_pages_source` | string | oui | Méthode de calcul du nombre de pages (`local`…) |
| `jstor_item_id` | string | oui | Identifiant JSTOR de l'article |
| `source_lang` | string | oui | Méthode de détection de la langue (`fulltext`…) |
| `date_added` | string (ISO 8601) | non | Date d'ajout de la notice |
| `date_modified` | string (ISO 8601) | non | Date de dernière modification |
| `auteurs` | array[object] | oui | Auteurs associés — voir [§ auteurs](#auteurs-array) |
| `keywords` | array[object] | oui | Mots-clés classifiés — voir [§ keywords](#keywords-array) |
| `dispo` | array[object] | oui | Disponibilité en ligne par source — voir [§ dispo](#dispo-array) |
| `chemin_fichier` | array[string] | oui | Chemins locaux vers les fichiers texte récupérés (chemins machine, non portables !) |
| `topic_analysis` | object | oui | Résultats de l'analyse thématique — voir [§ topic_analysis](#topic_analysis-object) |
| `ris_raw` | string | oui | Données brutes RIS issues de Worldcat — **non distribuées** (propriété intellectuelle) |

---

### `auteurs` (array)

Liste des auteurs tels qu'identifiés dans la notice. La jointure avec la collection `authors` se fait via le champ `cle`.

| Champ | Type | Description |
|---|---|---|
| `patronyme` | string | Nom tel qu'il figure dans la notice Worldcat |
| `cle` | string | Clé de jointure avec la collection `authors` |

---

### `keywords` (array)

Mots-clés utilisés pour le scraping, enrichis d'une classification thématique à quatre niveaux.

| Champ | Type | Description |
|---|---|---|
| `kw` | string | Mot-clé brut utilisé lors du scraping |
| `lemme` | string | Lemme normalisé regroupant les variantes (langues, graphies) |
| `souscategorie` | string | Sous-catégorie thématique |
| `categorie` | string | Catégorie thématique |
| `theme` | string | Thème de niveau supérieur |

---

### `dispo` (array)

Disponibilité en ligne vérifiée pour chaque source.

| Champ | Type | Description |
|---|---|---|
| `source` | string | Source vérifiée (`jstor`, `cairn`, `persee`) |
| `statut` | int \| boolean | Résultat : `1` = disponible, `false` = non disponible |
| `fiabilite` | float | Score de fiabilité de la vérification (0–1) |

---

### `topic_analysis` (object)

Résultats de la modélisation thématique appliquée aux textes intégraux.

| Champ | Type | Description |
|---|---|---|
| `topic_id` | string | Identifiant du topic attribué (ex. `ART_8`) |
| `num_origine` | int | Numéro du topic dans le modèle d'origine |
| `label` | string | Étiquette du topic (peut être vide) |
| `source_type` | string | Type de source ayant servi à l'analyse (`analyse_articles`…) |

---

> Note : pour le champ `chemin_fichier`, il s'agit surtout pour moi, lorsque mes fichiers étaient peu organisés, de pouvoir les retrouver plus facilement.


---


## Collection `authors`

Chaque document représente un auteur identifié dans au moins une notice de la collection `references`.

### Champs de premier niveau

| Champ | Type | Optionnel | Description |
|---|---|---|---|
| `_id` | ObjectId | non | Identifiant unique MongoDB |
| `idmysql` | int | non | Identifiant hérité de la modélisation relationnelle initiale |
| `cle` | string | non | Clé de jointure avec la collection `references` (format `Nom, Prénom_horodatage`) |
| `nom_complet` | string | non | Nom complet normalisé (`Nom, Prénom`) |
| `Nom` | string | non | Nom de famille |
| `Prenom` | string | oui | Prénom |
| `identifiants` | object | oui | Identifiants dans les référentiels externes — voir [§ identifiants](#identifiants-object) |
| `genre` | object | oui | Genre — voir [§ genre](#genre-object) |
| `genre_impute` | object | oui | Issu de l'imputation Namsor, pour ne pas confondre avec le genre de l'auteur réel |
| `langue` | array[object] | oui | Langue(s) de publication — voir [§ langue](#langue-array) |
| `nationalites` | array[object] | oui | Nationalité(s) — voir [§ nationalites](#nationalites-array) |
| `date_naissance` | object | oui | Date de naissance — voir [§ date_naissance](#date_naissance-object) |
| `lieux_naissance` | array[object] | oui | Lieu(x) de naissance — voir [§ lieux_naissance](#lieux_naissance-array) |
| `sujets_etude` | array[object] | oui | Domaines de spécialité — voir [§ sujets_etude](#sujets_etude-array) |
| `formation` | array[object] | oui | Parcours de formation — voir [§ formation](#formation-array) |
| `emploi` | array[object] | oui | Parcours professionnel — voir [§ emploi](#emploi-array) |
| `methode_recup` | string | oui | Pipeline de récupération des données (`idref_viaf_worldcat`, `undetermined`…) |
| `raw_data_traces` | array[object] | oui | Traces des données brutes sources — voir [§ raw_data_traces](#raw_data_traces-array) |
| `info_saisie` | object | oui | Métadonnées de traitement — voir [§ info_saisie](#info_saisie-object) |

---

### `identifiants` (object)

Tous les sous-champs sont optionnels ; leur présence dépend des référentiels ayant retourné un résultat pour l'auteur.

| Champ | Type | Référentiel |
|---|---|---|
| `PPN_IDREF` | string | IdRef (ABES) |
| `PPN_VIAF` | string | VIAF |
| `isni` | string | ISNI |
| `orcid` | string (URL) | ORCID |
| `wikipedia` | string | QID Wikidata (ex. `Q112441795`) |
| `bnf` | string (URL ARK) | Bibliothèque nationale de France |
| `persee` | string (URL) | Persée |
| `scopusid` | string | Scopus |

---

### `genre` (object)

| Champ | Type | Description |
|---|---|---|
| `valeur` | string | Genre normalisé : `male` ou `female` |
| `sources` | array[string] | Source(s) ayant fourni l'information (`viaf_scraping`, `combine_root`…) |

---

### `langue` (array)

Langue(s) dans lesquelles l'auteur publie, issues du VIAF ou de Wikidata.

| Champ | Type | Description |
|---|---|---|
| `code_iso` | string | Code ISO 639-2 (`ger`, `eng`, `fre`…) |
| `sources` | array[string] | Source(s) de l'information |

---

### `nationalites` (array)

| Champ | Type | Description |
|---|---|---|
| `nom_pays` | string | Nom du pays en anglais |
| `sources` | array[string] | Source(s) de l'information |

---

### `date_naissance` (object)

**`date_naissance.details`**

| Champ | Type | Description |
|---|---|---|
| `valeur_iso` | string | Date en format ISO ou partiel (`1950`, `+1950-02-05T00:00:00Z`, `19XX`) |
| `sources` | array[string] | Source(s) de la valeur (`combine_root`, `combine_wiki`…) |

---

### `lieux_naissance` (array)

| Champ | Type | Description |
|---|---|---|
| `code_lieu` | string | QID Wikidata du lieu (ex. `Q1741` pour Vienne) |
| `sources` | array[string] | Source(s) de l'information |

---

### `sujets_etude` (array)

Deux formes coexistent selon la source : les données VIAF fournissent un libellé brut (`valeur`), les données Wikidata fournissent un QID normalisé (`code_occupation`). Les deux peuvent être présents dans le même document.

| Champ | Type | Optionnel | Description |
|---|---|---|---|
| `code_occupation` | string | oui | QID Wikidata de la profession ou spécialité (ex. `Q3621491`) |
| `valeur` | string | oui | Libellé brut issu du scraping VIAF (multilingue, non normalisé) |
| `sources` | array[string] | non | Source(s) de l'information |

> **Avertissement** : les `valeur` issues de VIAF sont hétérogènes (multilingues, granularité variable) et nécessiteraient une normalisation avant toute exploitation quantitative.

---

### `formation` (array)

Parcours de formation récupéré principalement depuis ORCID et Wikidata.

| Champ | Type | Optionnel | Description |
|---|---|---|---|
| `institution` | string | non | Nom de l'établissement |
| `diplome` | string | oui | Intitulé du diplôme ou de la qualification |
| `periode` | string | oui | Période (`YYYY-MM-DD to YYYY-MM-DD` ou `present`) |
| `annee_debut` | int | oui | Année de début |
| `annee_obtention` | int | oui | Année d'obtention du diplôme |
| `wikidata_id` | string | oui | QID Wikidata de l'établissement |
| `sources` | array[string] | non | Source(s) de l'information |
| `location` | object (GeoJSON) | oui | Coordonnées géographiques — voir [§ location](#location-geojson-point) |

---

### `emploi` (array)

Parcours professionnel récupéré principalement depuis ORCID et Wikidata.

| Champ | Type | Optionnel | Description |
|---|---|---|---|
| `institution` | string | non | Nom de l'établissement |
| `poste` | string | oui | Intitulé du poste et du département |
| `periode` | string | oui | Période (`YYYY-MM-DD to YYYY-MM-DD` ou `present`) |
| `annee_debut` | int | oui | Année de début |
| `annee_fin` | int | oui | Année de fin |
| `en_cours` | boolean | oui | Indique si le poste est toujours occupé |
| `wikidata_id` | string | oui | QID Wikidata de l'établissement |
| `sources` | array[string] | non | Source(s) de l'information |
| `location` | object (GeoJSON) | oui | Coordonnées géographiques — voir [§ location](#location-geojson-point) |

---

### `location` (GeoJSON Point)

Présent dans les objets `formation` et `emploi`. Suit la spécification GeoJSON standard (RFC 7946).

| Champ | Type | Description |
|---|---|---|
| `type` | string | Toujours `"Point"` |
| `coordinates` | array[float] | `[longitude, latitude]` — ordre GeoJSON standard |

> Les coordonnées proviennent de Wikidata via le QID de l'établissement. Elles permettent des requêtes géospatiales MongoDB natives (`$geoNear`, `$geoWithin`…).

---

### `raw_data_traces` (array)

Traces des données brutes conservées pour la traçabilité et la reproductibilité. La structure interne du champ `data` ou `extracted_data` varie selon la `source_origin`.

| Champ | Type | Description |
|---|---|---|
| `source_origin` | string | Pipeline source : `combine`, `combine_wiki`, `viaf_scraping`, `viaf_scraping_details`, `viaf_scraping_gender`, `orcid` |
| `date` | string (ISO 8601) | Horodatage du scraping ou du traitement |
| `data` | object | Données brutes (présent pour `combine`, `viaf_scraping`, `orcid`) |
| `extracted_data` | object | Données extraites et partiellement normalisées (présent pour `viaf_scraping_details`, `viaf_scraping_gender`) |

---

### `info_saisie` (object)

| Champ | Type | Description |
|---|---|---|
| `date_traitement` | string (ISO 8601) | Date du premier traitement du document |
| `date_modified` | string (ISO 8601) | Date de la dernière modification |
