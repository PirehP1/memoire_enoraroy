# Analyse textuelle et thématique du corpus

Ce dossier regroupe les scripts Python utilisés pour la construction, le prétraitement et l'analyse lexicale et thématique du corpus. Les scripts sont numérotés dans leur ordre d'exécution recommandé et forment un pipeline linéaire (relativement). Les scripts préfixés d'un underscore (`_`) sont soit des modules auxiliaires, soit des outils complémentaires indépendants qui peuvent être lancés à n'importe quelle étape une fois le corpus propre disponible.

L'ensemble du pipeline repose sur le paquet [`lexploreur`](https://github.com/leodumont/lexploreur) pour la construction et l'exploitation des corpus JSON annotés par spaCy.

S'il aurait été envisageable de faire une Analyse Factorielle des Correspondances en Python, l'outil en ligne [AnalyseSHS](http://analyse.univ-paris1.fr/) a été utilisé afin de seuiller en ligne, configurer les interfaces et exporter tous les résultats plus facilement.

Pour l'étude des cooccurrences de "barbar*", je renvoie au protocole disponible dans [ce repo](https://github.com/SLamasse/matcoocs/tree/main).

Un grand merci aux développeurs de ces outils, qui m'ont bien servi !

---

Fichiers d'entrée principaux :

| Fichier / dossier | Description |
|---|---|
| `raw_texts/` | Fichiers texte bruts au format `{doc_id}.txt` |
| `meta_lemmatisation.csv` | Métadonnées : `doc_id`, `year`, `title` |
| `stopwords-en.txt` | Liste de mots vides (anglais) |
| `_cooc_exclusions.py` | Module partagé : segments d'exclusion et tokens bibliographiques |
| `data_reseau/edges_author_pub.csv` | Arêtes du réseau de coauteurs (requis par `08b` uniquement) |
| `data_reseau/nodes_all.csv` | Nœuds du réseau avec métadonnées (requis par `08b` uniquement) |

Fichiers de sortie principaux (dossiers configurables dans chaque script) :

| Fichier | Produit par |
|---|---|
| `output/corpus_complet/corpus_complet.json` | `01` |
| `output/corpus_propre/corpus_propre.json` | `01bis` |
| `output/stats_corpus/stats_generales.txt`, `group_sizes_par_annee.csv`, `top30_lemmes.csv`, `01–05_*.pdf` | `02` |
| `output/stats_corpus_propre/stats_generales_propre.txt`, `comparaison_complet_propre.*`, `top30_lemmes_propre.csv`, `01–08_*.pdf` | `02bis` |
| `output/distribution_temporelle/planche_tokens_documents.pdf` | `03` |
| `output/zipf/zipf_table.csv`, `zipf_parametres.csv`, `zipf_plot_*.pdf` | `04` |
| `output/jenks_contingency/jenks_decoupage.pdf`, `jenks_periodes.csv`, `contingency_table*.csv` | `05` |
| `output/contingency_annees/contingency_raw.csv`, `contingency_norm.csv`, `corpus_stats.csv` | `05_test` |
| `output/sweep/coherence_sweep.pdf`, `coherence_sweep.csv`, `k*/topics_lda.txt` | `06` |
| `output/topic_modelling/lda_model/`, `gamma_df.csv`, `beta_df.csv`, `topics_lda.*`, `top_docs_par_topic.txt`, `01_plot_tm.pdf`, `02_topics_par_an.pdf` | `07` |
| `output/topic_modelling/topic_mean_gamma_by_year.csv`, `05_ruptures_courbes_individuelles.pdf`, `06_evolution_globale_stacked.pdf`, `ldavis.html` | `08` |
| `output/boxplots_auteurs/boxplots_auteurs_par_topic.png`, `synthese_auteurs_par_topic.csv` | `08b` |
| `output/evaluation_lda/convergence.pdf`, `evaluation.txt` | `09` |
| `output/topic_modelling/07_concentration_thematique.pdf`, `08_topic_dominant.pdf`, `09_correlation_topics.pdf`, `analyse_gamma.txt` | `10` |
| `output/tfidf/fig_exemple_document.pdf`, `fig_top_par_annee.pdf`, `tfidf_top20_par_doc.csv`, `tfidf_top_par_annee.csv`, `tfidf_top_par_annee.tex` | `11` |
| `concordances/concordances_*.csv`, `concordances_*.tex`, `iramuteq_corpus_*.txt` | `_kwic_1`, `_kwic_2` |
| `output/progression_temporelle/frequency_year.pdf`, `density_year.pdf`, `frequences_par_annee.csv` | `_progression_lemme` |

---




## Description des scripts

### `_cooc_exclusions.py` — Module partagé : listes d'exclusion et nettoyage bibliographique

Module importé par `01bis` (et tout script de cooccurrence). Il définit trois structures utilisées pour le nettoyage des textes bruts. `EXCLUSION_SEGMENTS` est une liste de tuples `(segment, catégorie)` regroupant les titres bibliographiques contenant la forme *barbar\**, les prénoms *Barbara* (y compris leurs variantes OCR collées) et les toponymes ou noms propres interférents. `BIB_TOKENS` est une liste de tokens courts à supprimer : abréviations latines (*ibid.*, *op. cit.*), chiffres romains isolés, mots vides multilingues parasites. `BIB_PATTERNS` est une liste de regex (vide par défaut, extensible). Le module a également deux fonctions utilitaires : `is_excluded(contexte)` pour tester si un contexte KWIC contient un segment d'exclusion, et `clean_text_bib(texte)` pour appliquer l'ensemble des couches de nettoyage sur un texte brut.

---

### `01_creation_corpus_global.py` — Construction du corpus brut

À partir des fichiers `.txt` du dossier `raw_texts/` et du fichier de métadonnées `meta_lemmatisation.csv`, le script filtre les documents hors de la plage 1975–2025 et exclut le document identifié par `EXCLUDE_ID` (document multilingue hors sujet). Les textes retenus sont annotés par spaCy (`en_core_web_lg`) via la fonction `corpus()` de lexploreur, sans NER. La sortie est un fichier JSON structuré : chaque entrée contient les métadonnées du document et la liste de ses `lexical_features` (token, lemme, POS). S'il détecte que `corpus_complet.json` existe déjà, il ne ré-annote pas. Pour forcer la ré-annotation, supprimer le fichier JSON.

Sortie : `output/corpus_complet/corpus_complet.json`.

---

### `01bis_creation_corpus_propre.py` — Construction du corpus nettoyé

Construit un second corpus lexploreur à partir des mêmes textes bruts, après application de deux couches de nettoyage définies dans `_cooc_exclusions.py` : (1) suppression des segments d'exclusion par substitution regex insensible à la casse, (2) suppression des tokens et patterns bibliographiques. Un rapport de nettoyage est imprimé en console : réduction de caractères par document, nombre de suppressions par catégorie, documents inchangés. Un mode audit (`AUDIT_SAMPLE`) permet d'afficher un aperçu avant/après pour un échantillon de documents ayant subi des modifications. Ce corpus est la source de toutes les analyses lexicales et thématiques ultérieures (scripts 05 à 11).

Sortie : `output/corpus_propre/corpus_propre.json`.

---

### `02_stat_desc.py` — Statistiques descriptives du corpus brut

Analyse `corpus_complet.json` sans aucun filtre (toutes POS, aucun stopword) afin de caractériser la matière première avant prétraitement. La vue lexicale est construite à deux niveaux : par année (pour la DTM et les `group_sizes`) et par document (pour la distribution des longueurs). La DTM est construite via `CountVectorizer` de scikit-learn. Les indicateurs produits sont : nombre d'occurrences, de lemmes uniques et d'hapax (globaux et par année), longueur minimale, maximale, moyenne et médiane des documents. Cinq graphiques PDF sont générés : volumes par année (`features`, `types`, `hapax`), évolution temporelle des trois courbes superposées, et histogramme de la distribution des longueurs de documents.

Sorties : `stats_generales.txt`, `group_sizes_par_annee.csv`, `top30_lemmes.csv`, `01–05_*.pdf`.

---

### `02bis_stat_desc_propre.py` — Statistiques descriptives du corpus propre et comparaison

Complément du script précédent, appliqué à `corpus_propre.json`. Produit les mêmes indicateurs descriptifs, puis construit un tableau comparatif complet/propre sur six métriques (occurrences, lemmes uniques, hapax, longueurs) avec calcul automatique du taux de réduction. Si les fichiers de stats du corpus complet (`output/stats_corpus/`) sont disponibles, trois graphiques supplémentaires superposent les deux courbes (complet en bleu foncé, propre en bleu clair) avec une zone grisée représentant l'impact du prétraitement.

Sorties : `stats_generales_propre.txt`, `comparaison_complet_propre.txt`, `comparaison_complet_propre.csv`, `group_sizes_par_annee.csv`, `top30_lemmes_propre.csv`, `01–08_*.pdf`.

---

### `03_distrib_temporelle_corpus.py` — Distribution temporelle tokens/documents

Génère une planche PDF à deux panneaux. Le premier panneau représente le volume de tokens par année (corpus d'analyse uniquement). Le second superpose deux séries en barres : la base bibliographique MongoDB (fond bleu, toutes les références anglophones disponibles) et le corpus d'analyse (rouge, avant-plan), permettant de visualiser le taux de couverture du corpus sur la littérature disponible. MongoDB est interrogé en direct à l'exécution ; si l'instance est inaccessible, le script produit la planche sans la couche bibliographique.

Sortie : `output/distribution_temporelle/planche_tokens_documents.pdf`.

---

### `04_loi_zipf.py` — Vérification empirique de la loi de Zipf

Charge les lemmes du corpus avec filtres (longueur ≥ 3, alphabétique, POS configurables), calcule les fréquences et range les lemmes par rang décroissant. Le modèle de Zipf est appliqué selon la méthodologie de [Codedrome](https://codedrome.substack.com/p/zipfs-law-in-python) : `f(r) = C × (1/r)` où `C` est la fréquence du lemme de rang 1 et `α` est fixé à 1. Quatre graphiques sont produits en combinant deux échelles (linéaire et log-log) et deux configurations (données brutes seules, puis comparaison avec la courbe théorique). Un tableau CSV exporte rang, lemme, fréquence observée, fréquence prédite et écart.

Sorties : `zipf_table.csv`, `zipf_parametres.csv`, `zipf_plot_absolu.pdf`, `zipf_plot_absolu_theorique.pdf`, `zipf_plot_loglog.pdf`, `zipf_plot_loglog_theorique.pdf`.

---

### `05_tab_cont_lemme_annee.py` — Tableau de contingence avec périodisation Jenks

Découpe le corpus en périodes homogènes par la méthode de Natural Breaks de Jenks, appliquée aux volumes de tokens **cumulés** par année, de façon à obtenir des tranches temporelles contenant des masses documentaires comparables. Le nombre de périodes `K` est déterminé automatiquement par la règle de Sturges appliquée au nombre d'années non vides. Une année supplémentaire (`--supp-year`) peut être exclue du calcul Jenks et des décomptes de fréquences tout en restant signalée dans le mapping par le flag `is_supp=True`. Le tableau de contingence lemmes × périodes produit est conçu pour être analysé sur [http://analyse.univ-paris1.fr/](http://analyse.univ-paris1.fr/) (spécificités, AFC).

Sorties : `jenks_decoupage.pdf`, `jenks_periodes.csv`, `contingency_table.csv`, `contingency_table_norm.csv`.

---

### `05_test_tab_cont_lemme_annee_sans_categorisation.py` — Tableau de contingence annuel (sans périodisation)

Variante complémentaire du script précédent : conserve le découpage annuel au lieu d'agréger par période Jenks. Construit le tableau de contingence lemmes × années (occurrences brutes), puis calcule les profils lignes (fréquences relatives de chaque lemme sur les années). Un tableau de statistiques par année est également produit (volume de tokens, lemmes distincts, hapax, top 3 lemmes). Permet de comparer ce que l'on gagne / perd à la périodisation

Sorties : `contingency_raw.csv`, `contingency_norm.csv`, `corpus_stats.csv`.

---

### `06_sweep_lda.py` — Recherche du nombre optimal de topics (sweep LDA)

Pour chaque valeur de `k` dans `NUM_TOPICS_RANGE` (par défaut 4 à 20), entraîne un modèle LDA Gensim avec une seed fixe (`LDA_SEED = 1826`) et `LDA_PASSES = 20` passes, puis calcule la cohérence c_v. Les mots caractéristiques de chaque topic sont sauvegardés dans un sous-dossier `k{N}/topics_lda.txt`. Une courbe de cohérence est produite avec mise en évidence du maximum. L'utilisateur doit consulter à la fois `coherence_sweep.pdf` et les fichiers `topics_lda.txt` pour choisir `k` de manière qualitative et quantitative avant de passer au script suivant.

Sorties : `output/sweep/coherence_sweep.pdf`, `coherence_sweep.csv`, `k*/topics_lda.txt`.

---

### `07_lda_k.py` — Modèle LDA final avec k choisi

Entraîne le modèle LDA définitif avec le `k` sélectionné après consultation du sweep, en conservant exactement les mêmes paramètres (seed, passes, stopwords, filtres POS) pour que la cohérence c_v soit identique à celle observée dans le sweep. Les matrices `gamma` (documents × topics) et `beta` (topics × mots) sont exportées en CSV. Un graphique lexploreur des topics est produit, ainsi qu'un graphique en barres empilées montrant l'occurrence de chaque topic par année (seuil de présence configurable via `TOPIC_PRESENCE_THR`). Un fichier texte liste les dix documents les plus représentatifs par topic.

Sorties : `lda_model/`, `gamma_df.csv`, `beta_df.csv`, `topics_lda.txt/.csv`, `top_docs_par_topic.txt`, `01_plot_tm.pdf`, `02_topics_par_an.pdf`.

---

### `08_plot_lda.py` — Visualisation de l'évolution thématique

Lit `gamma_df.csv` et `topics_lda.csv` produits par `07` et génère deux graphiques d'évolution temporelle basés sur la probabilité moyenne γ par topic et par année. Le premier graphique représente les courbes individuelles par topic avec détection automatique de ruptures par l'algorithme PELT (`ruptures`). Le second est un graphique en barres empilées des proportions relatives, permettant de lire l'évolution de la structure thématique du corpus. Une visualisation interactive HTML (pyLDAvis) est également générée si le paquet est installé.

Sorties : `topic_mean_gamma_by_year.csv`, `05_ruptures_courbes_individuelles.pdf`, `06_evolution_globale_stacked.pdf`, `ldavis.html` (optionnel).

---

### `08b_boxplot_auteur_lda.py` — Distribution du nombre d'auteurs par topic

Script exploratoire croisant la matrice gamma LDA avec les données du réseau de coauteurs vu précédement. Pour chaque publication présente dans le réseau, le topic dominant est attribué par argmax de γ, et le nombre d'auteurs est lu depuis `nodes_all.csv`. Un boxplot horizontal est tracé pour chaque topic, avec superposition des points individuels et indication de la médiane, de la moyenne et des quartiles. La composante connexe principale (CCP) et les autres composantes sont distinguées dans le décompte.

L'idée est de voir s'il peut exister un lien entre nb d'auteurs par publication et la thématique LDA.

Sorties : `output/boxplots_auteurs/boxplots_auteurs_par_topic.png`, `synthese_auteurs_par_topic.csv`.

---

### `09_evaluation_LDA.py` — Évaluation du modèle LDA

Évalue le modèle produit par `07` sur trois axes. (I) **Cohérence c_v** globale et par topic (le score global doit correspondre à celui du sweep). (II) **Convergence Δβ** : un nouveau modèle est entraîné passe par passe et la variation moyenne de la matrice β (norme L1) est tracée ; une convergence atteinte se manifeste par un Δβ tendant vers 0 et se stabilisant. (III) **Perplexité** : un split 75/25 par tirage aléatoire (seed fixe) est utilisé pour entraîner un modèle sur les données d'entraînement et mesurer la log-perplexité sur les données de test ; une valeur entre −5 et −10 est attendue pour ce type de corpus.

Sorties : `output/evaluation_lda/convergence.pdf`, `evaluation.txt`.

---

### `10_analyse_gamma.py` — Analyse de la distribution thématique (matrice γ)

Produit trois graphiques d'analyse de la matrice γ selon l'approche des distributions continues. (I) **Concentration thématique** : histogramme de l'entropie de Shannon normalisée de γ par document (H/H_max = 0 → document concentré sur un seul topic ; H/H_max = 1 → distribution uniforme sur tous les topics). (II) **Topic dominant** : nombre de documents par topic (argmax de γ) avec indication du γ moyen du topic dominant. (III) **Corrélations** : heatmap Pearson des corrélations entre topics, permettant d'identifier les topics co-occurrents (r fort positif) et les topics exclusifs (r fort négatif).

Sorties : `07_concentration_thematique.pdf`, `08_topic_dominant.pdf`, `09_correlation_topics.pdf`, `analyse_gamma.txt`.

---

### `11_tf_idf.py` — TF-IDF par document et par année

Calcule le TF-IDF à deux niveaux de granularité. Au niveau **document**, `CountVectorizer` + `TfidfTransformer` de scikit-learn produisent les scores de spécificité lexicale de chaque texte ; un barplot horizontal des 20 lemmes les plus spécifiques est généré pour un document sélectionnable en argument (`--doc`). Au niveau **année**, la vue lexicale est agrégée par année avant vectorisation, et un tableau des top-N lemmes par année est produit en PDF, CSV et LaTeX. Les titres des documents sont récupérés depuis `meta_lemmatisation.csv` si disponible.

Sorties : `output/tfidf/fig_exemple_document.pdf`, `fig_top_par_annee.pdf`, `tfidf_top20_par_doc.csv`, `tfidf_top_par_annee.csv`, `tfidf_top_par_annee.tex`.

---

### `_1_kwic_interactive_version.py` — Concordancier KWIC interactif

Outil en ligne de commande permettant d'extraire toutes les occurrences d'un lemme dans le corpus avec leur contexte gauche et droit (fenêtre configurable via `--window`, défaut 8). La boucle interactive invite l'utilisateur à saisir un lemme à la fois ; les résultats sont affichés en console (20 premières lignes) et exportés en CSV et LaTeX dans le dossier `--output`. La normalisation typographique (tirets Unicode, apostrophes) évite les faux négatifs dus aux artefacts de numérisation.

Sorties : `concordances/concordances_{lemme}.csv`, `concordances_{lemme}.tex`.

---

### `_2_kwic_to_iramuteq.py` — Conversion des concordances au format IRaMuTeQ

À exécuter après `_1_kwic_interactive_version.py`. Lit tous les fichiers `concordances_*.csv` d'un dossier source et génère pour chacun un corpus texte compatible IRaMuTeQ, où chaque segment correspond à une ligne KWIC (contexte gauche + pivot + contexte droit) précédée d'un en-tête de variables étoilées (`*YEAR_<année> *DOC_<titre>`). Les espaces dans les titres sont remplacés par des underscores (contrainte IRaMuTeQ) et les titres sont tronqués à 50 caractères.

Sorties : `concordances/iramuteq_corpus_{lemme}.txt`.

---

### `_progression_lemme.py` — Distribution temporelle de lemmes cibles

Analyse la progression temporelle d'un ou plusieurs lemmes cibles (configurables via `TARGET_LEMMAS` ou `--lemmas`) en construisant un corpus DataFrame et une DTM alignés. La colonne `_other_` de la DTM — comptabilisant tous les tokens non ciblés — permet à `plot_feature_distrib` de lexploreur de calculer correctement les densités (fréquences relatives par million de tokens). Deux graphiques sont produits selon le mode `--plot_type` : fréquence absolue et densité par million de mots. Un CSV exporte les fréquences absolues et PMW par année.

Sorties : `output/progression_temporelle/frequency_year.pdf`, `density_year.pdf`, `frequences_par_annee.csv`.

---

## Notes

Le pipeline est séquentiel pour les scripts 01 à 11 : chaque script dépend de la sortie du précédent. Les scripts auxiliaires préfixés `_` peuvent être lancés à n'importe quel moment après la construction de `corpus_propre.json`. `08b` requiert en outre des fichiers de réseau externes (`data_reseau/`) qui ne font pas partie du pipeline principal.

La seed LDA (`LDA_SEED = 1826`) est identique dans `06`, `07`, `08`, `09` et `10`. Ne pas la modifier pour garantir la reproductibilité et la correspondance des scores de cohérence entre le sweep et le modèle final.

Les filtres lexicaux (`EXCLUDE_POS`, `STOPWORDS`, longueur minimale) sont identiques dans les scripts 05, 05_test, 06 et 07 : toute modification dans l'un doit être répercutée dans les autres pour maintenir la cohérence du pipeline.

---

## Dépendances

```bash
pip install spacy pandas tqdm lexploreur scikit-learn matplotlib seaborn \
            gensim jenkspy ruptures scipy numpy pymongo
python -m spacy download en_core_web_lg
pip install pyldavis   # optionnel, pour ldavis.html (script 08)
```

Versions testées :

```
Python       3.11
spaCy        3.7
gensim       4.3
scikit-learn 1.4
pandas       2.2
matplotlib   3.8
jenkspy      0.3
ruptures     1.1
lexploreur   (voir dépôt GitHub)
```

