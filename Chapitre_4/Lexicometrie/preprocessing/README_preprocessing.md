# Prétraitement du corpus — correction des artefacts OCR

Ce dossier regroupe les scripts Python utilisés pour le nettoyage des artefacts OCR du corpus de textes bruts, préalablement à la lemmatisation. Les données sont lues depuis `corpus_propre.json` et les corrections appliquées aux fichiers `.txt` correspondants dans `raw_texts/`. Les chemins sont centralisés dans `config.py`. Les scripts sont numérotés dans leur ordre d'exécution recommandé, bien que les dépendances entre eux ne soient pas strictes.

La chaîne de traitement se décompose en trois blocs distincts, correspondant à trois types d'artefacts : les mots coupés en fin de ligne *avec* tiret (`01x`), les tokens anormalement longs issus de collages OCR (`02x`), et les mots coupés *sans* tiret visible (`03x`). Les blocs sont indépendants les uns des autres et peuvent être exécutés séparément, mais l'ordre intra-bloc doit être respecté.

---

Fichier d'entrée commun : `corpus_propre.json` (chemin configuré dans `config.py`)

Répertoire des textes bruts : `raw_texts/` (chemin configuré dans `config.py`)

Fichiers de décision partagés entre scripts (lecture/écriture) :

| Fichier | Rôle | Partagé entre |
|---|---|---|
| `pair_decisions.json` | Décisions par paire (token1, token2) — tiret | `01`, `03`, `03b` |
| `progress.json` | Décisions par position (doc_id, feat_idx) — tiret | `01`, `01c` |
| `merge_list.json` | Fusions validées [y] — tiret | `01`, `01b`, `01c` |
| `no_hyphen_decisions.json` | Décisions par paire — sans tiret | `03`, `03b`, `03c` |
| `no_hyphen_merge_list.json` | Fusions validées [y] — sans tiret | `03`, `03b`, `03c` |
| `no_hyphen_doc_scores.json` | Score OCR par document — sans tiret | `03`, `03b`, `03c` |

Fichiers de sortie principaux :

| Fichier | Produit par |
|---|---|
| `merge_list.json`, `pair_decisions.json`, `progress.json` | `01` |
| `auto_skipped.json` | `01` |
| `auto_merge_log.json`, `auto_merge_skipped_uppercase.json` | `01c` |
| `long_tokens_corrections.json`, `long_tokens_progress.json` | `02` |
| `no_hyphen_merge_list.json`, `no_hyphen_decisions.json` | `03`, `03b` |
| `rapport_no_hyphen.txt`, `no_hyphen_applied_log.json` | `03c` |
| `backups/<timestamp>/` | `01`, `01b`, `01c`, `02`, `03c` |

---

## Description des scripts

### `01_recoller_mots_coupes.py` — Arbitrage interactif des mots coupés avec tiret

Parcourt `corpus_propre.json` et repère les tokens se terminant par un tiret (-, ‐, ‑, ‒, –, —, ⁃) immédiatement suivis d'un token alphabétique, signature d'un mot coupé en fin de ligne par l'OCR. Trois niveaux de traitement sont appliqués dans l'ordre : exclusion automatique par règle (radicaux en `-eenth`, composés `anglo-*`, ordinaux suivis de `century`), application silencieuse des décisions déjà prises pour une paire identique dans une session précédente (via `pair_decisions.json`), puis soumission interactive des cas nouveaux. Les paires sont présentées par fréquence décroissante dans le corpus : une décision s'applique automatiquement à toutes les occurrences de la même paire. La progression est sauvegardée toutes les 5 décisions et à chaque interruption (`q`).

L'application aux fichiers `.txt` est proposée en fin de session.

Sorties : `merge_list.json`, `pair_decisions.json`, `progress.json`, `auto_skipped.json`, `backups/<timestamp>/`.

---

### `01b_appliquer_decision_recollage.py` — Généralisation des fusions validées au corpus

Lit `merge_list.json` et recherche dans `corpus_propre.json` tous les documents contenant les mêmes paires de tokens consécutifs. La comparaison est stricte, casse comprise. Pour chaque fichier `.txt` concerné, un backup `{doc_id}_backup.txt` est créé avant modification (jamais écrasé). Le script est idempotent : `applied_corrections.json` mémorise les corrections déjà appliquées au niveau `(doc_id, token1, token2)` ; seules les paires nouvelles depuis la dernière exécution sont retraitées.

Sorties : `applied_corrections.json`, `rapport_application.txt`, `backups/<timestamp>/`.

---

### `01c_auto_fusion.py` — Recollage automatique du résidu

Fusionne automatiquement toutes les paires tiret + token non encore traitées, sans arbitrage interactif. Les décisions humaines `[n]` existantes sont respectées. Exclusions supplémentaires par rapport à `01` : composés directionnels et temporels (`north-`, `early-`, `pre-`, etc., configurables via `DIRECTION_STEMS`) et fusions produisant une majuscule au milieu du mot résultant (comportement contrôlé par `SKIP_UPPERCASE_IN_MIDDLE`, activé par défaut). Ces derniers cas sont journalisés dans `auto_merge_skipped_uppercase.json` pour examen éventuel. Une confirmation est demandée avant toute écriture.

Sorties : `auto_merge_log.json`, `auto_merge_skipped_uppercase.json`, `backups/<timestamp>/`.

---

### `02_correction_artefact_ocr.py` — Nettoyage interactif des tokens trop longs

Détecte les tokens alphabétiques dépassant un seuil de longueur dans `corpus_propre.json` — signe d'un collage OCR (`barbarianscame`, `seventhcentury`…). Le seuil est calculé selon une stratégie configurable (`THRESHOLD_STRATEGY` : `fixed`, `median`, `q3`, `p90`…) et ne descend jamais en dessous de `THRESHOLD_FLOOR`. Pour chaque token détecté, l'utilisateur saisit la segmentation correcte (mots séparés par des espaces) ou passe avec `[s]` / `[sk]` pour ignorer le token ou le document entier. La progression est sauvegardée toutes les 5 décisions. L'application aux `.txt` est proposée en fin de session.

Sorties : `long_tokens_progress.json`, `long_tokens_corrections.json`, `backups/<timestamp>/`.

---

### `02b_correction_ocr_ciblee.py` — Réparation manuelle ciblée par document

Script ponctuel de réparation sur une liste restreinte de `doc_id` à renseigner directement dans `DOC_IDS`. Utilise `wordsegment` pour segmenter les tokens longs (au-delà de `LONG_WORD_THRESHOLD` caractères, hors URLs). Un diff coloré AVANT/APRÈS est affiché dans le terminal et une confirmation est demandée avant toute écriture. Contrairement à `02`, ce script n'interroge pas `corpus_propre.json` : il opère directement sur les fichiers `.txt`.

Sortie : `backups_manual_repair/{doc_id}_{timestamp}.txt.bak` (dans le répertoire `raw_texts/`).

---

### `03_detect_mots_coupes_sans_tirets.py` — Détection sans tiret — approche dictionnaire

Détecte les paires de tokens qui forment un mot coupé en fin de ligne sans tiret visible, artefact fréquent dans les PDF mal traités. Deux modes de détection sont appliqués : mode A pour les fragments très courts (token gauche ≤ `SHORT_MAX_LEN` caractères, toujours soumis à l'utilisateur) ; mode B pour les fragments de longueur intermédiaire (`SHORT_MAX_LEN` < len ≤ `DICT_MAX_LEN`), soumis uniquement si la concaténation est un mot anglais valide selon `pyspellchecker` et que les deux fragments ne sont pas tous deux des mots valides séparément. Les décisions de `pair_decisions.json` (script `01`) sont importées silencieusement. Chaque décision est mémorisée par paire et généralisée à toutes les occurrences du corpus. Un score OCR par document est calculé (nb de problèmes confirmés / nb de tokens).

Sorties : `no_hyphen_decisions.json`, `no_hyphen_merge_list.json`, `no_hyphen_doc_scores.json`, `rapport_no_hyphen.txt`.

---

### `03b_detect_mots_coupes_sans_tirets.py` — Détection sans tiret — approche PMI

Approche complémentaire de `03`, sans dictionnaire externe. Repose sur le constat qu'un fragment OCR est par définition rare dans le corpus et possède un collocate quasi-exclusif. Le PMI (Pointwise Mutual Information) est calculé sur tous les bigrammes adjacents ; une paire est retenue si `PMI ≥ PMI_THR`, `freq_bigram ≥ MIN_BIGRAM_FREQ`, et si `t1` appartient aux tokens les plus rares (fréquence ≤ percentile `RARE_PCT`). Les paramètres sont surchargeables en ligne de commande (`--rare_pct`, `--pmi_thr`, `--min_freq`). Les décisions déjà prises dans `no_hyphen_decisions.json` (sessions précédentes ou via `03`) sont respectées silencieusement. Les paires sont présentées par fréquence décroissante, puis par PMI décroissant.

Sorties : `no_hyphen_decisions.json`, `no_hyphen_merge_list.json`, `no_hyphen_doc_scores.json`, `rapport_no_hyphen.txt`.

---

### `03c_appliquer_decisions.py` — Application des recollages sans tiret

Applique `no_hyphen_merge_list.json` aux fichiers `.txt`, en ciblant chaque document listé dans le champ `docs` de chaque entrée. La regex de remplacement inclut des word-boundaries pour éviter les faux positifs sur des sous-chaînes, avec fallback sans boundary pour les contextes OCR atypiques. Le script est idempotent : `no_hyphen_applied_log.json` mémorise les paires déjà traitées. Un rapport de statistiques par document est exporté.

Sorties : `no_hyphen_applied_log.json`, `stats/stats_no_hyphen_applied.txt`, `backups/<timestamp>/`.

---

## Notes

Les scripts `01`, `02` et `03`/`03b` sont interactifs et conçus pour être relancés : la progression est sauvegardée à chaque session et reprise automatiquement au lancement suivant. Les scripts `01b`, `01c` et `03c` sont non interactifs (hors confirmation initiale) et idempotents.

`pair_decisions.json` est partagé en lecture par `03` et `03b` : toute paire déjà arbitrée dans `01` y est silencieusement reconnue, ce qui évite de retraiter les mêmes fragments avec et sans tiret.

Le champ `docs` dans `no_hyphen_merge_list.json` liste les identifiants de tous les documents contenant la paire concernée. `03c` s'appuie sur ce champ pour cibler les fichiers `.txt` à modifier, sans reparcourir le corpus JSON.

---

## Dépendances

```
pip install tqdm numpy pyspellchecker wordsegment
```

Versions testées :

```
Python          3.11
tqdm            4.66
numpy           1.26
pyspellchecker  0.8
wordsegment     1.3
```

`wordsegment` est utilisé uniquement dans `02b` ; les autres scripts n'en dépendent pas.
