# Base de données

## Contexte et architecture

Elle repose sur des notices bibliographiques collectées via Worldcat par scraping, puis enrichies progressivement à travers plusieurs étapes de redocumentarisation.

La base est stockée sous forme NoSQL (MongoDB), dans deux collections au format `.json` : `references` et `authors`.

Ce choix architectural est aussi un choix épistémologique : là où un modèle relationnel aurait contraint chaque notice à un schéma prédéfini et identique pour toutes, le format document permet de préserver la singularité de chaque notice. La richesse ou la pauvreté des informations associées à une référence ou à un auteur est en elle-même une information sur l'objet d'étude. Chaque document peut avoir des champs totalement différents des autres au sein de la même collection, et peut évoluer sans fragiliser l'ensemble de la base.

---

## Deux collections

### `references`

Chaque document représente une publication scientifique scrapée depuis Worldcat. Il contient notamment :

```json
{
  "_id": "ObjectId",
  "idmysql": "int (héritage de la première modélisation relationnelle)",
  "title": "string",
  "year": "int",
  "type_of_reference": "string",
  "doi": "string",
  "keywords": ["..."],
  "abstract": "string",
  "auteurs": [{"cle": "...", "...": "..."}],
  "dispo": ["..."],
  "topic_analysis": {"...": "..."},
  "..."
}
```

La jointure avec la collection `authors` se fait via le champ `cle` présent dans le tableau `auteurs`. Aucune contrainte d'intégrité référentielle n'est imposée par la base elle-même : il convient d'en tenir compte lors des agrégations.

### `authors`

Chaque document représente un auteur identifié dans les notices. Il contient notamment :

```json
{
  "_id": "ObjectId",
  "idmysql": "int",
  "cle": "string (identifiant de jointure)",
  "nom_complet": "string",
  "Nom": "string",
  "Prenom": "string",
  "identifiants": {"...": "..."},
  "genre": {"...": "..."},
  "langue": ["..."],
  "nationalites": ["..."],
  "date_naissance": {"...": "..."},
  "sujets_etude": ["..."],
  "..."
}
```

---

## Ce que la base contient, plus que les analyses du mémoire ont pu mobiliser

La base de données est plus riche que ce qu'ont mobilisé les analyses du mémoire. Plusieurs ensembles de données ont été constitués mais n'ont pas pu être pleinement exploités, faute de temps ou de normalisation suffisante. Ils sont néanmoins présents dans les documents et représentent des pistes de recherche à part entière.

### Propriétés Wikidata sur les auteurs

Les auteurs ont été enrichis avec des propriétés issues de Wikidata, stockées sous la forme de l'ontologie Wikidata (propriétés `Pxxx`, entités `Qxxx`). Ce choix garantit l'**interopérabilité** avec d'autres corpus et bases de données du web : il est possible de croiser ces données avec n'importe quelle ressource exposant des identifiants Wikidata.

### `sujets_etude`

Le champ `sujets_etude` recense les domaines de spécialité des auteurs, récupérés depuis Wikidata et/ou VIAF. Ces données auraient pu permettre une analyse fine des positionnements disciplinaires au sein de l'espace de publication, mais leur exploitation se heurte à l'absence de normalisation : les libellés sont hétérogènes, multilingues, et de granularité variable. Une normalisation préalable (alignement sur un référentiel commun, regroupement par domaine) serait nécessaire avant toute analyse quantitative.

### Institutions d'emploi et de formation

Des informations sur les institutions de rattachement des auteurs (emploi, formation) ont été partiellement collectées — essentiellement via Wikidata et Orcid. Ces données sont présentes dans la base pour un sous-ensemble des auteurs, mais leur couverture est inégale. Elles auraient permis une géographie institutionnelle du champ, en croisant notamment les affiliations avec les identifiants Wikidata des établissements (eux-mêmes liés à des coordonnées géographiques, des pays, des types d'institution, etc.).

---

## Ce qui n'est pas livré — raisons légales et propriété intellectuelle

Pour des raisons légales, les données propriétaires de Worldcat ne sont pas incluses dans cette base :

- les **numéros OCLC** des notices ;
- les **fichiers RIS bruts** tels qu'exportés depuis Worldcat.

En revanche, l'ensemble des données issues de l'enrichissement ultérieur (appariements Wikidata, VIAF, imputations, classifications thématiques, analyses) est bien présent dans la base livrée.

---

## Reproductibilité et réutilisabilité

Le choix du format `.json` et de l'ontologie Wikidata pour les entités nommées vise à garantir la potentielle réutilisation de la base dans des chaînes de traitement plus larges (pipelines d'analyse, web sémantique, APIs). La documentation se réduit à deux fichiers `.json` exportables depuis MongoDB, là où un modèle relationnel équivalent aurait impliqué une dizaine de tables interdépendantes.

Les pipelines de traitement associés à la constitution de cette base sont documentés séparément.
