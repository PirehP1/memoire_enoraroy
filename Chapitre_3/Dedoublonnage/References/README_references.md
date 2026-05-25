## Dossier `references/`

Une même publication peut être indexée plusieurs fois dans Worldcat sous des notices légèrement différentes (variantes de titre, encodages distincts, titres partiels). Si, pour le doi, ces cas semblent relever de l'évidence, puisque deux publications différentes ne peuvent pas avoir le même identifiant unique, la tâche se révèle plus complexe lorsqu'il s'agit de comparer des titres.

### Scripts de détection

**`01_dedoublonnage_reference_doi.py`** — Détecte les références partageant un même DOI après normalisation (suppression des préfixes `doi:` ou `https://doi.org/`, mise en minuscules). Le script distingue deux cas : si les années des références sont identiques ou proches (écart ≤ 1 an), les notices sont considérées comme de vrais doublons ; si les années sont trop éloignées (> 1 an), une référence est conservée par année afin d'éviter des fusions abusives entre rééditions ou publications distinctes partageant un DOI erroné ou réutilisé. La référence conservée est celle possédant le plus grand nombre de champs renseignés (`info_score`). Avant suppression, certains champs de disponibilité (`Persée`, `JSTOR`, `Cairn`) sont fusionnés afin de ne pas perdre d'information.

**`02_dedoublonnage_reference_issn.py`** — Détecte les doublons de références partageant un même ISSN normalisé (suppression des tirets, espaces et caractères parasites ; conservation du premier ISSN lorsqu'une notice en contient plusieurs). Ce script vise principalement les doublons de périodiques ou d'articles indexés sous plusieurs notices bibliographiques mais rattachés au même identifiant de revue.

**`03_dedoublonnage_reference_levenshtein.py`** — Pipeline en quatre passes successives : regroupement par année exacte, puis par `secondary_title` (Levenshtein ≥ 0,85), puis comparaison des titres principaux (Levenshtein ≥ 0,88), enfin vérification qu'au moins un auteur est commun aux deux références. Union-Find pour la transitivité.

**`03_dedoublonnage_reference_levenshtein_SANS_AUTEUR.py`** — Idem, mais sans auteur !

**`04_dedoublonnage_reference_chapitre`** — Ciblé sur les chapitres d'ouvrages collectifs : regroupe par `secondary_title` (titre du livre), extrait le numéro de chapitre depuis le titre (chiffres arabes, romains, mots en français/anglais/allemand/espagnol), puis compare les titres nettoyés des indicateurs de chapitre par Levenshtein ≥ 0,90.

**`05_dedoublonnage_reference_permissif.py`** — Complète le pipeline Levenshtein en couvrant deux angles laissés ouverts par les scripts précédents. Premier apport : détection par contenance stricte — si le titre normalisé le plus court (minimum 10 caractères) est littéralement inclus dans le plus long, la paire est retenue indépendamment du ratio Levenshtein. Second apport : les références sans `secondary_title` ou sans année, jusqu'ici isolées ou ignorées, sont intégrées dans une phase *catch-all* qui les compare contre l'ensemble du corpus sans contrainte d'année. Le `secondary_title` est par ailleurs utilisé comme filtre d'exclusion (ratio < 0,20 et absence de contenance) plutôt que comme critère de regroupement, ce qui rend le script plus permissif que le `03`. Le pipeline se déroule en cinq étapes : partition du corpus en *main stream* (année et `secondary_title` présents) et *catch-all* ; comparaison par fenêtre d'année (±1 an) sur le main stream ; comparaison exhaustive pour le catch-all ; résolution de la transitivité par Union-Find ; export JSON. DOI et ISSN ayant déjà été traités en amont, ce script n'y touche pas. Ce script est considéré comme une dernière étape, pour éventuellement vérifier les derniers doublons restants.

### Sortie

Même format JSON que pour les auteurs, avec suggestion `keep` / `delete` / `skip` à vérifier manuellement.

### Script d'application

**`06_appliquer_dedoublon_references.py`** — Script unifié d'application, compatible avec tous les fichiers JSON produits par les scripts de détection (02 à 05). Prend le fichier de décisions en argument ; sans flag --apply, s'exécute en mode dry run (aucune écriture en base). Pour chaque cluster validé (exactement un keep, au moins un delete), effectue les opérations suivantes dans l'ordre : calcul de la valeur maximale des champs de disponibilité (Persée, JSTOR, Cairn) et de leurs indices de fiabilité associés sur l'ensemble du cluster ; conservation de l'année la plus ancienne ; transfert des mots-clés (reference_keyword) des notices supprimées vers la notice conservée ; suppression des notices delete. La mise à jour en base est conditionnelle : si aucun champ ne change, aucun UPDATE n'est émis. Les clusters marqués skip ou dépourvus de delete sont ignorés silencieusement ; les clusters malformés (nombre de keep différent de 1) génèrent un avertissement.
