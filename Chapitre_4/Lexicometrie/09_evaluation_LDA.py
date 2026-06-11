#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SCRIPT 09 — ÉVALUATION DU MODÈLE LDA

Lit le modèle produit par 07_LDA_k.py et l'évalue sur trois axes :

  I.   Cohérence c_v   → score global + par topic
  II.  Convergence Δβ  → variation de la matrice topics→mots passe par passe
  III. Perplexité      → log-perplexité sur corpus de test (tirage 75/25)

SORTIES
-------
  output/evaluation_lda/
    convergence.pdf     ← courbe Δβ par passe
    evaluation.txt      ← bilan chiffré

STRUCTURE ATTENDUE
------------------
  <dossier du script>/
  ├── output/topic_modelling/lda_model/   ← produit par 07_LDA_k.py
  │   ├── lda.model
  │   └── dictionary.gensim
  ├── output/corpus_propre/corpus_propre.json
  └── stopwords-en.txt

USAGE
-----
  python 09_evaluation_LDA.py

PRÉ-REQUIS
----------
  python 07_LDA_k.py

REPRODUCTIBILITÉ
----------------
  Mêmes paramètres que 07_LDA_k.py (LDA_SEED, LDA_PASSES, EXCLUDE_*).
  La cohérence calculée ici est identique à celle du sweep (06_sweep_LDA.py).

DÉPENDANCES
-----------
  pip install gensim lexploreur numpy matplotlib
=======================================================================
"""

import pathlib
import warnings
import logging
import sys
import random

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from gensim import corpora
from gensim.models import LdaModel
from gensim.models.coherencemodel import CoherenceModel
from lexploreur.corpus import lexical_view

warnings.filterwarnings("ignore", category=DeprecationWarning)
logging.basicConfig(format="%(levelname)s : %(message)s", level=logging.WARNING)

BASE_DIR = pathlib.Path(__file__).resolve().parent

CORPUS_JSON    = BASE_DIR / "output" / "corpus_propre" / "corpus_propre.json"
STOPWORDS_PATH = BASE_DIR / "stopwords-en.txt"

# Ces valeurs doivent être identiques à 07_LDA_k.py
LDA_SEED   = 1826
LDA_PASSES = 20

EXCLUDE_POS = ["PUNCT", "CCONJ", "DET", "ADP", "PRON", "PART", "SCONJ",
               "SPACE", "SYM", "NUM", "X", "AUX", "INTJ"]

EXCLUDE_TOKENS = ["-", "--", "…", "'s", "n't", "'re", "'ve", "'d", "'ll",
                  "https", "http", "see", "however", "also", "university",
                  "die", "von", "der", "den", "zur", "lo", "di", "lot",
                  "o6p", "xl", "dq", "на", "g6", "g12", "iii", "ap", "rrr", "rr",
                  "wkh", "oc", "robert", "kerala", "bäyrämova", "torigni",
                  "avranches", "dl", "……", "reproduction", "tí", "press", "walter"]

MODEL_DIR = BASE_DIR / "output" / "topic_modelling" / "lda_model"
EVAL_DIR  = BASE_DIR / "output" / "evaluation_lda"
EVAL_DIR.mkdir(parents=True, exist_ok=True)


def load_model_and_corpus():
    model_path = MODEL_DIR / "lda.model"
    dict_path  = MODEL_DIR / "dictionary.gensim"

    for p in [model_path, dict_path, CORPUS_JSON, STOPWORDS_PATH]:
        if not p.exists():
            print(f"[ERREUR] Fichier introuvable : {p}")
            sys.exit(1)

    print(f"Chargement du modèle : {model_path}")
    lda_model  = LdaModel.load(str(model_path))
    dictionary = corpora.Dictionary.load(str(dict_path))
    num_topics = lda_model.num_topics
    print(f"→ {num_topics} topics | {len(dictionary):,} formes")

    with open(STOPWORDS_PATH, encoding="utf-8", errors="replace") as f:
        stopwords = [line.strip() for line in f if line.strip()]

    print("lexical_view() …")
    df_lv = lexical_view(
        str(CORPUS_JSON),
        feature_to_extract = "lemma",
        stopwords          = stopwords,
        lowercase          = True,
        exclude_pos        = EXCLUDE_POS,
        exclude_tokens     = EXCLUDE_TOKENS,
    )
    df_lv["lemma"] = df_lv["lemma"].apply(lambda t: [w for w in t if len(w) > 1])

    # On ne conserve que les mots présents dans le dictionnaire du modèle
    dict_words = set(dictionary.values())
    texts      = [[w for w in doc if w in dict_words] for doc in df_lv["lemma"]]
    corpus_bow = [dictionary.doc2bow(t) for t in texts]

    print(f"→ {len(corpus_bow)} documents | vocabulaire restreint au dictionnaire du modèle")
    return lda_model, dictionary, corpus_bow, texts, num_topics


# ──────────────────────────────────────────────────────────────────────
#  I. COHÉRENCE  (même logique que le sweep → score identique)
# ──────────────────────────────────────────────────────────────────────

def evaluate_coherence(lda_model, dictionary, texts):
    print("\n── I. COHÉRENCE ──────────────────────────────────────────────")

    coherence_model = CoherenceModel(
        model      = lda_model,
        texts      = texts,
        dictionary = dictionary,
        coherence  = "c_v",
        processes  = 1,
    )
    score_global = coherence_model.get_coherence()
    print(f"  Cohérence c_v globale : {score_global:.4f}")
    print(f"  (> 0.5 : excellent ; 0.4–0.5 : correct)")

    per_topic = coherence_model.get_coherence_per_topic()
    print("\n  Cohérence c_v par topic :")
    for i, score_t in enumerate(per_topic):
        top_words = " / ".join(w for w, _ in lda_model.show_topic(i, topn=5))
        flag = "★" if score_t >= 0.4 else ("?" if score_t >= 0.3 else "✗")
        print(f"    Topic {i:2d} [{flag}] {score_t:.4f}  —  {top_words}")

    return score_global, per_topic


def evaluate_convergence(dictionary, corpus_bow, num_topics):
    """
    Suit la variation de β (matrice topics→mots) passe par passe.
    Δβ → 0  =  les distributions ne bougent plus  =  convergence atteinte.
    Si Δβ reste élevé ou oscille → augmentez LDA_PASSES dans 07_LDA_k.py.
    """
    print("\n── II. CONVERGENCE ───────────────────────────────────────────")
    print(f"  Entraînement passe par passe ({LDA_PASSES} passes, seed={LDA_SEED}) …")

    np.random.seed(LDA_SEED)
    lda = LdaModel(
        corpus_bow,
        num_topics   = num_topics,
        id2word      = dictionary,
        passes       = 1,
        eval_every   = None,
        random_state = LDA_SEED,
    )

    delta_beta_history = []
    beta_prev = lda.get_topics().copy()

    for pass_num in range(2, LDA_PASSES + 1):
        lda.update(corpus_bow)
        beta_curr = lda.get_topics()
        delta = float(np.mean(np.abs(beta_curr - beta_prev)))
        delta_beta_history.append((pass_num, delta))
        beta_prev = beta_curr.copy()
        print(f"  Passe {pass_num:3d}/{LDA_PASSES} | Δβ : {delta:.2e}")

    passes_idx = [x[0] for x in delta_beta_history]
    delta_vals = [x[1] for x in delta_beta_history]

    plt.figure(figsize=(10, 5))
    plt.plot(passes_idx, delta_vals, marker="o", color="#d7191c")
    plt.title(
        f"Convergence LDA ({num_topics} topics, {LDA_PASSES} passes, seed={LDA_SEED})\n"
        "Δβ = variation moyenne de la matrice topics→mots entre deux passes"
    )
    plt.xlabel("Passes")
    plt.ylabel("Δβ moyen (norme L1)")
    plt.grid(alpha=0.3)
    out = EVAL_DIR / "convergence.pdf"
    plt.savefig(str(out), format="pdf", bbox_inches="tight")
    plt.close()
    print(f"\n  → {out.name}")
    print("  Δβ tend vers 0 et se stabilise → convergence atteinte.")
    print("  Δβ reste élevé ou oscille → augmentez LDA_PASSES dans 07_LDA_k.py.")

    return lda


def evaluate_perplexity(lda_conv, corpus_bow, num_topics):
    """
    Divise le corpus en train (75 %) / test (25 %) par tirage aléatoire.
    Le tirage aléatoire évite de biaiser le split selon l'ordre des
    documents (ex : toutes les années récentes dans le test).

    Interprétation : valeur négative, plus proche de 0 = meilleure
    généralisation. Entre −5 et −10 : bon résultat pour ce type de corpus.
    """
    print("\n── III. PERPLEXITÉ ───────────────────────────────────────────")

    indices = list(range(len(corpus_bow)))
    random.seed(LDA_SEED)
    random.shuffle(indices)
    split        = int(0.75 * len(indices))
    train_corpus = [corpus_bow[i] for i in indices[:split]]
    test_corpus  = [corpus_bow[i] for i in indices[split:]]
    print(f"  Train : {len(train_corpus)} docs | Test : {len(test_corpus)} docs")
    print(f"  (tirage aléatoire 75/25, seed={LDA_SEED})")

    np.random.seed(LDA_SEED)
    lda_train = LdaModel(
        train_corpus,
        num_topics   = num_topics,
        id2word      = lda_conv.id2word,
        passes       = LDA_PASSES,
        random_state = LDA_SEED,
    )

    perplexity = lda_train.log_perplexity(test_corpus)
    print(f"\n  Log-perplexité (corpus de test) : {perplexity:.4f}")
    print("  Entre −5 et −10 → bon résultat pour ce type de corpus.")
    print("  Plus proche de 0 → meilleure généralisation.")

    return perplexity


if __name__ == "__main__":

    lda_model, dictionary, corpus_bow, texts, num_topics = load_model_and_corpus()

    coherence, per_topic = evaluate_coherence(lda_model, dictionary, texts)
    lda_conv             = evaluate_convergence(dictionary, corpus_bow, num_topics)
    perplexity           = evaluate_perplexity(lda_conv, corpus_bow, num_topics)

    # Bilan texte
    lines = [
        "ÉVALUATION DU MODÈLE LDA",
        f"Nb de topics      : {num_topics}",
        f"Cohérence c_v     : {coherence:.4f}",
        f"Log-perplexité    : {perplexity:.4f}",
        "",
        "Cohérence c_v par topic :",
    ]
    for i, score_t in enumerate(per_topic):
        flag = "★" if score_t >= 0.4 else ("?" if score_t >= 0.3 else "✗")
        lines.append(f"  Topic {i:2d} [{flag}] {score_t:.4f}")
    (EVAL_DIR / "evaluation.txt").write_text("\n".join(lines), encoding="utf-8")

    print(f"  Nombre de topics  : {num_topics}")
    print(f"  Cohérence c_v     : {coherence:.4f}")
    print(f"  Log-perplexité    : {perplexity:.4f}")
    print(f"  Courbe converg.   : {EVAL_DIR / 'convergence.pdf'}")
    print(f"  Bilan             : {EVAL_DIR / 'evaluation.txt'}")
