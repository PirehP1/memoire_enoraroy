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

