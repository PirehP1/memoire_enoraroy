# Enrichissement des métadonnées via l'API CrossRef

Ce dossier contient les scripts utilisés pour compléter automatiquement les métadonnées de la base à partir de l'API publique de CrossRef. L'API permet d'interroger gratuitement les données d'une publication à partir de son DOI et retourne un JSON structuré. Avec plus de 20 000 publications ayant un DOI dans la base, cette ressource permettait d'automatiser largement la récupération d'informations. La documentation de l'API est disponible à l'adresse `https://api.crossref.org/swagger-ui/index.html`.

D'abord, la totalité des réponses JSON sont collectées et sauvegardées localement (puisque j'ai beaucoup de références en base, il semblait pertinent de pouvoir arrêter et relancer le script sans repartir de zéro en cas d'interruption, et ne pas causer de souci sur la BDD). Ensuite, les informations sont insérées dans la table `reference` selon un principe de non-écrasement : un champ déjà renseigné n'est jamais remplacé. Pour les auteurs, le script vérifie l'existence de liens dans la table de liaison `ecriture` avant d'en créer de nouveaux, qu'il s'agisse d'auteurs déjà présents dans `authors` ou d'auteurs à créer. Parmi les informations les plus utiles figurent la langue et les auteurs associés à une référence.

La décision de ne pas automatiser la mise à jour du champ `type_of_reference` résulte d'une limite identifiée après coup. Lors des premières vérifications des JSON retournés, les références échantillonnées étaient majoritairement des chapitres ou des articles, ce qui avait laissé croire que la taxonomie CrossRef était suffisamment proche des codes RIS utilisés en base. C'est à l'analyse plus systématique qu'est apparue la diversité réelle des types exposés par l'API — `edited-book`, `monograph`, `reference-entry`, `posted-content`, `peer-review`, entre autres — dont le mapping vers les codes RIS est parfois ambigu. Ce champ n'est donc pas traité automatiquement ; la base conserve les valeurs `CHAP` et `JOUR` héritées des imports RIS. Ce point est signalé ici car il pourrait être implémenté dans une version ultérieure, à condition de définir explicitement la table de correspondance entre la taxonomie CrossRef et les codes RIS souhaités.

> NOTE : WorldCat pointe parfois vers des DOI vides ou invalides, qui ne renvoient rien chez CrossRef. Ces cas sont enregistrés dans le dump avec `"found": false` et ignorés lors de l'étape d'insertion.

> NOTE : Le `User-Agent` envoyé à CrossRef contient un placeholder d'adresse mail à remplacer par votre adresse réelle. CrossRef offre un accès au « polite pool » — moins sujet aux limitations de débit — en échange de cette information.

---

## Dépendances

```
pip install mysql-connector-python requests
```

---

## Description des scripts

### `crossref_full_dump.py`

Interroge l'API CrossRef pour chaque référence de la base disposant d'un DOI et sauvegarde la réponse complète dans `crossref_full_dump.json`. La reprise est gérée nativement : les identifiants déjà traités sont mémorisés entre deux exécutions. Une interruption clavier déclenche une sauvegarde propre. En cas de rate-limit (HTTP 429), le script marque une pause de 30 secondes et réessaie, jusqu'à trois tentatives avant d'abandonner la référence concernée.

**Sortie :** `crossref_full_dump.json`

### `crossref_to_db.py`

Lit `crossref_full_dump.json` et enrichit la base selon le principe de non-écrasement décrit ci-dessus : ise à jour des champs vides de `reference`, création des auteurs absents dans `authors`, et établissement des liens dans `ecriture` si aucun auteur n'y est déjà associé à la référence.
