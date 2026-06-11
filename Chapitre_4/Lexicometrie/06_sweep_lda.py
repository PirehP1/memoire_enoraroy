#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
  SCRIPT 06 — SWEEP LDA : RECHERCHE DU NOMBRE OPTIMAL DE TOPICS

DESCRIPTION
-----------
Pour chaque k dans NUM_TOPICS_RANGE, entraîne un LdaModel avec la
même seed fixe, calcule la cohérence c_v et sauvegarde les topics.

Reproductibilité : une seule seed → résultats similaires à chaque
ré-exécution.

SORTIES
-------
  output/sweep/
    coherence_sweep.pdf         ← courbe de cohérence
    coherence_sweep.csv         ← scores bruts
    k04/topics_lda.txt          ← mots par topic pour k=4
    k05/topics_lda.txt          ← …
    ...

STRUCTURE ATTENDUE
------------------
  <dossier du script>/
  ├── output/corpus_propre/corpus_propre.json
  ├── stopwords-en.txt
  └── output/sweep/             ← créé automatiquement

DÉPENDANCES
-----------
  pip install gensim lexploreur numpy pandas matplotlib
"""

import pathlib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from lexploreur.corpus import *
from lexploreur.utils import *
from gensim import corpora
from gensim.models import LdaModel, CoherenceModel

BASE_DIR = pathlib.Path(__file__).resolve().parent

CORPUS_JSON    = BASE_DIR / "output" / "corpus_propre" / "corpus_propre.json"
STOPWORDS_PATH = BASE_DIR / "stopwords-en.txt"

NUM_TOPICS_RANGE = range(4, 21)   # ← plage de k à tester
LDA_PASSES       = 20
LDA_SEED         = 1826           # ← seed fixe — ne pas modifier
TOPIC_TOPN       = 15             # ← nb de mots affichés par topic

EXCLUDE_POS = ["PUNCT", "CCONJ", "DET", "ADP", "PRON", "PART", "SCONJ",
               "SPACE", "SYM", "NUM", "X", "AUX", "INTJ"]

EXCLUDE_TOKENS = ["-", "--", "…", "'s", "n't", "'re", "'ve", "'d", "'ll",
                  "https", "http", "see", "however", "also", "university",
                  "die", "von", "der", "den", "zur", "lo", "di", "lot",
                  "o6p", "xl", "dq", "на", "g6", "g12", "iii", "ap", "rrr", "rr",
                  "wkh", "oc", "robert",
                  "dl", "……", "reproduction", "tí", "press", "permission",
                  "reproduce", "copyright"]

SWEEP_DIR = BASE_DIR / "output" / "sweep"
SWEEP_DIR.mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":

    # 1. Stopwords
    with open(STOPWORDS_PATH, encoding="utf-8", errors="replace") as f:
        STOPWORDS = [line.strip() for line in f if line.strip()]

    # 2. Vue lexicale
    df_lv = lexical_view(
        str(CORPUS_JSON),
        feature_to_extract = "lemma",
        stopwords          = STOPWORDS,
        lowercase          = True,
        exclude_pos        = EXCLUDE_POS,
        exclude_tokens     = EXCLUDE_TOKENS,
    )
    df_lv["lemma"] = df_lv["lemma"].apply(
        lambda tokens: [t for t in tokens if len(t) > 1]
    )
    print(f"{len(df_lv)} documents chargés")

    # 3. Dictionary + corpus BoW
    dictionary = corpora.Dictionary(df_lv["lemma"])
    # dictionary.filter_extremes(no_below=5)   # décommenter pour retirer le bruit rare
    corpus_bow = [dictionary.doc2bow(t) for t in df_lv["lemma"]]
    print(f"Vocabulaire : {len(dictionary):,} formes | {len(corpus_bow):,} documents")

    # 4. Sweep
    results = []

    for n in NUM_TOPICS_RANGE:
        print(f"\nk={n} …", end=" ", flush=True)

        np.random.seed(LDA_SEED)
        lda_model = LdaModel(
            corpus_bow,
            num_topics   = n,
            id2word      = dictionary,
            passes       = LDA_PASSES,
            random_state = LDA_SEED,     # ← même seed pour tous les k
        )

        cm = CoherenceModel(
            model      = lda_model,
            texts      = df_lv["lemma"].to_list(),
            dictionary = dictionary,
            coherence  = "c_v",
            processes  = 1,
        )
        coh = cm.get_coherence()
        print(f"c_v = {coh:.4f}")

        results.append({"k": n, "coherence_cv": coh})

        # Sauvegarde des mots par topic pour ce k
        out_dir = SWEEP_DIR / f"k{n:02d}"
        out_dir.mkdir(exist_ok=True)

        lines = [f"k={n} | passes={LDA_PASSES} | seed={LDA_SEED} | c_v={coh:.4f}", ""]
        for topic_id in range(n):
            topic_words = lda_model.get_topic_terms(topic_id, topn=TOPIC_TOPN)
            label = " / ".join(dictionary[wid] for wid, _ in topic_words[:5])
            lines.append(f"Topic {topic_id:2d} — {label}")
            lines.append("-" * 50)
            for word_id, freq in topic_words:
                lines.append(f"  {dictionary[word_id]:<38} {freq:.5f}")
            lines.append("")
        (out_dir / "topics_lda.txt").write_text("\n".join(lines), encoding="utf-8")

    # 5. CSV et graphe de cohérence
    df = pd.DataFrame(results)
    df.to_csv(SWEEP_DIR / "coherence_sweep.csv", index=False, encoding="utf-8-sig")

    best_k   = int(df.loc[df["coherence_cv"].idxmax(), "k"])
    best_coh = df["coherence_cv"].max()

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(df["k"], df["coherence_cv"], "o-", color="#2c7bb6", lw=2.5, ms=8)
    ax.scatter([best_k], [best_coh], color="#d7191c", s=160, zorder=5,
               label=f"Maximum : k={best_k}  (c_v={best_coh:.4f})")
    ax.axvline(best_k, ls="--", color="#d7191c", lw=1.5)
    ax.set_xlabel("Nombre de topics (k)", fontsize=12)
    ax.set_ylabel("Cohérence c_v", fontsize=12)
    ax.set_title(
        f"Cohérence LDA selon le nombre de topics\n"
        f"(1 run × {LDA_PASSES} passes, seed = {LDA_SEED})",
        fontsize=12,
    )
    ax.set_xticks(list(NUM_TOPICS_RANGE))
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.4)
    plt.tight_layout()
    plt.savefig(str(SWEEP_DIR / "coherence_sweep.pdf"), format="pdf", bbox_inches="tight")
    plt.close()
    print(f"  Consultez output/sweep/coherence_sweep.pdf")
    print(f"  Consultez output/sweep/k*/topics_lda.txt pour lire les topics")
    print(f"  Puis lancez 07_LDA_k.py avec le k de votre choix")
