# Analyse linguistique et nationale du corpus

Ce dossier regroupe les scripts R utilisés pour l'analyse de la distribution des langues de publication et des nationalités d'auteurs, développée au chapitre d'analyse du mémoire. Les données sont extraites depuis MongoDB à l'exécution de chaque script ; aucun fichier intermédiaire n'est partagé entre eux. Les scripts sont numérotés dans leur ordre d'exécution recommandé. Ils sont tous indépendants les uns des autres : aucun ne consomme la sortie d'un autre, et peuvent donc être lancés dans n'importe quel ordre une fois la base MongoDB disponible. La numérotation reflète la progression analytique du corpus global vers l'étude de cas plus précise d'une nationalité, ici polonaise, et suivent assez logiquement mon cheminement de pensée.

---

Fichiers d'entrée : base MongoDB `references_biblio_mongo` (instance locale)

| Collection | Champs utilisés |
|---|---|
| `references` | `_id`, `auteurs`, `language`, `language_name`, `year` |
| `authors` | `cle`, `nationalites` |

Fichiers de sortie principaux (à configurer via `OUTPUT_DIR` dans chaque script) :

| Fichier | Produit par |
|---|---|
| `Stackbar_Freq_1975_2025_mongo.pdf`, `Stackbar_Occ_1975_2025_mongo.pdf` | 01 |
| `table_langues.tex` | 02 |
| `nationalites_100pct.pdf` | 03 |
| `evolution_anglais_top6_par_annee.pdf`, `stats_anglais_top6.tex` | 04 |
| `heatmap_langues_polonais_pct.pdf`, `heatmap_langues_polonais_n.pdf`, `table_langues_polonais_decennie.tex` | 05 |
| Tableau LaTeX (console) | 06 |
| `tableau_flux_nouveaux_auteurs.tex`  | 07 |

---

## Description des scripts

### `01_repartition_temporelle_langue.R` — Distribution temporelle des langues (corpus global)

Pour l'ensemble du corpus, le script extrait les champs `language_name` et `year` depuis MongoDB, agrège les publications par langue et par année, et retient les 6 langues les plus représentées sur l'ensemble de la période (les autres sont regroupées sous `"Autre"`). Deux graphiques en barres empilées sont produits pour la période 1975–2025 : l'un en fréquences relatives, l'autre en volumes absolus. Le script est encapsulé dans une fonction `generate_viz_period()` paramétrée par année de début et de fin, ce qui permet de la rappeler sur des sous-périodes sans modification du code.

Sorties : `Stackbar_Freq_<période>_mongo.pdf`, `Stackbar_Occ_<période>_mongo.pdf`.

---

### `02_part_temporelle_top6_langue.R` — Parts annuelles des top 6 langues et table de synthèse

Complément statistique du script précédent. À partir du même corpus, le script calcule pour les 6 langues dominantes leur part annuelle, lisse les séries par une moyenne mobile sur 5 ans (via `zoo::rollmean`), puis extrait des valeurs ponctuelles aux années clés définies dans `years_key` (par défaut 1980, 2000, 2020). Ces valeurs sont exportées dans un tableau LaTeX.

Sortie : `table_langues.tex`.

---

### `03_nationalite_nouveaux_auteurs.R` — Nationalité des nouveaux auteurs par année d'entrée

Pour chaque auteur, l'année de première publication est reconstituée depuis la collection `references`. Les nationalités sont récupérées depuis la collection `authors` et pondérées : un auteur plurinational contribue à hauteur de 1/N pour chacun de ses N pays (de sorte que la somme des poids vaut 1 par auteur). Les auteurs sans nationalité renseignée sont conservés dans la catégorie `"Non identifié"`.

Le top 6 est calculé en excluant la nationalité la plus fréquente (rang 1) — le paramètre `slice(2:7)` l'exprime explicitement. Deux graphiques en barres empilées sont construits : l'un en volumes absolus pondérés, l'autre en proportions annuelles (100 %). Un tableau LaTeX de synthèse par décennie est également produit (imprimé en console).

Sortie : `nationalites_100pct.pdf`.

---

### `04_anglicisation_top_nationalite.R` — Évolution de la part de l'anglais par nationalité (Top 6)

Mesure, pour les 6 nationalités non anglophones les plus représentées dans le corpus, l'évolution annuelle de la proportion de publications en anglais entre 1975 et 2025. Les pays anglophones (`United States of America`, `United Kingdom`, `Australia`) sont exclus en amont pour ne pas biaiser la mesure. Les auteurs plurinationaux sont comptés une fois pour chaque nationalité non anglophone.

L'anglais est détecté sur le champ brut `language` via l'expression régulière `^en$|^eng$|^english$`. Les trajectoires sont lissées par une moyenne mobile sur 3 ans. L'épaisseur des courbes encode visuellement le volume de publications selon une transformation `[log10(n)]^PUISSANCE` (par défaut 3.6), s'inspirant du procédé de Minard. Un tableau de statistiques descriptives (moyenne, min, max par nationalité) est exporté en LaTeX.

Sorties : `evolution_anglais_top6_par_annee.pdf`, `stats_anglais_top6.tex`.

---

### `05_langue_pour_une_nationalite.R` — Distribution linguistique pour une nationalité (étude de cas)

Pour une nationalité cible configurable via `PAYS_CIBLE` (par défaut `"Poland"`), le script visualise et quantifie les langues de publication année par année. L'inspiration vient du constat, fait sur le graphique `04`, d'une faible adoption de l'anglais par les auteurs polonais : ce script permet d'en documenter la dynamique fine.

Une publication co-signée par plusieurs auteurs de la nationalité cible ne compte qu'une seule fois. Les langues représentant moins de `SEUIL_LANGUE_PCT` % des publications sur l'ensemble de la période sont regroupées sous `"Autre"`. Deux heatmaps sont produites (fréquences relatives et volumes bruts), complétées d'un tableau LaTeX par décennie.

Sorties : `heatmap_langues_polonais_pct.pdf`, `heatmap_langues_polonais_n.pdf`, `table_langues_polonais_decennie.tex`.

---

### `06_statistiques_auteurs_polonais_multinationaux.R` — Multinationalité des auteurs polonais

Script exploratoire, complémentaire de `05`. Son objectif est de tester si la faible part de publications en anglais chez les auteurs polonais s'explique par un effet de champ (localisation française de la discipline altimédiéviste) ou par un effet de composition (présence de binationaux franco-polonais). Pour chaque auteur polonais, le statut multinational est calculé depuis les listes de nationalités en base ; le taux de multinationalité par décennie est ensuite croisé avec la liste des autres nationalités des auteurs plurinationaux. Un tableau LaTeX de la distribution linguistique par décennie est également produit.

> le taux de multinationalité calculé par décennie (`pct_multinational`) est rapporté au nombre de relations auteur-publication, et non au nombre d'auteurs distincts. Cela gonfle légèrement les décennies les plus productives mais est cohérent avec l'approche des autres scripts.

Sorties : tableaux imprimés en console ; aucun fichier exporté dans l'état actuel.

---

### `07_nationalite_nouveaux_auteurs.R` — Flux d'entrée dans le corpus par groupe de nationalité (tableau décennal)

Script complémentaire de `03`, recentré sur la production du tableau LaTeX. À partir des mêmes sources MongoDB, il reconstitue pour chaque auteur l'année de sa première apparition dans le corpus et lui assigne un groupe de nationalité parmi cinq catégories analytiques (États-Unis, Royaume-Uni, France, nationalité non identifiée, autres). Le schème de pondération 1/N pour les auteurs plurinationaux est identique à celui de `03`. Les parts annuelles sont calculées sur l'ensemble des cinq groupes — y compris « Autre » — de sorte que leur somme soit exactement égale à 100 % pour chaque année ; un `stopifnot` en assure la vérification systématique. Les données sont ensuite agrégées par décennie (1975–2025), les parts étant recalculées sur les effectifs décennaux agrégés afin de préserver la cohérence entre numérateurs et dénominateurs. Le script ne produit aucun graphique.

Sortie : `tableau_flux_nouveaux_auteurs.tex`.

---

## Notes

Tous les scripts interrogent directement MongoDB à l'exécution ; il n'y a pas de fichiers CSV intermédiaires. Une instance MongoDB locale sur `localhost:27017` est requise pour l'ensemble du pipeline.

Les auteurs plurinationaux sont systématiquement comptés une fois par nationalité (`unnest(nationalites)`), sauf dans `05` où la publication ne compte qu'une fois quelle que soit le nombre d'auteurs polynationaux qui la cosignent. Ces conventions sont documentées dans les commentaires de chaque script.

---

## Dépendances

```r
install.packages(c("mongolite", "tidyverse", "xtable", "scales", "zoo"))
```

Versions testées :

```
R           4.3
mongolite   2.7
tidyverse   2.0
xtable      1.8
scales      1.3
zoo         1.8
```

`cairo_pdf` (utilisé dans `05`) requiert que R soit compilé avec le support Cairo. Si ce n'est pas le cas, remplacer `device = cairo_pdf` par `device = "pdf"` dans les appels `ggsave()`.
