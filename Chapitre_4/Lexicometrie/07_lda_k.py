#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
  SCRIPT 07 — MODÈLE LDA FINAL APRÈS AVOIR CHOISI k

DESCRIPTION
-----------
Après avoir consulté coherence_sweep.pdf et les fichiers topics_lda.txt
produits par 06_sweep_LDA.py, indiquez le k choisi dans NUM_TOPICS
ci-dessous.

Ce script entraîne le modèle avec la même seed que 06_sweep_LDA.py :
la cohérence c_v obtenue est  identique à celle du sweep.

SORTIES
-------
  output/topic_modelling/
    lda_model/              ← modèle sauvegardé (rechargeable)
    gamma_df.csv            ← matrice documents × topics
    beta_df.csv             ← matrice topics × mots
    topics_lda.txt/.csv     ← mots caractéristiques par topic
    top_docs_par_topic.txt  ← top 10 documents par topic
    01_plot_tm.pdf          ← visualisation lexploreur
    02_topics_par_an.pdf    ← évolution temporelle (si années disponibles)

STRUCTURE ATTENDUE
------------------
  <dossier du script>/
  ├── output/corpus_propre/corpus_propre.json
  ├── meta_lemmatisation.csv   ← optionnel, pour les années
  └── stopwords-en.txt

PrÉ-REQUIS
----------
  python 06_sweep_LDA.py   → consulter output/sweep/ pour choisir k

DÉPENDANCES
-----------
  pip install gensim lexploreur numpy pandas matplotlib seaborn

"""

import json
import pathlib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

from lexploreur.corpus import *
from lexploreur.tm import *
from lexploreur.utils import *
from gensim import corpora
from gensim.models import LdaModel, CoherenceModel

# ──────────────────────────────────────────────────────────────────────
#  CONFIGURATION  ← mêmes valeurs que 06_sweep_LDA.py  +  votre k choisi
# ──────────────────────────────────────────────────────────────────────

BASE_DIR = pathlib.Path(__file__).resolve().parent

CORPUS_JSON    = BASE_DIR / "output" / "corpus_propre" / "corpus_propre.json"
STOPWORDS_PATH = BASE_DIR / "stopwords-en.txt"
META_CSV       = BASE_DIR / "meta_lemmatisation.csv"

NUM_TOPICS = 13     # ← CHOIX après consultation du sweep

# Ces valeurs doivent être identiques à 06_sweep_LDA.py
LDA_PASSES  = 30
LDA_SEED    = 1826
TOPIC_TOPN  = 20
TOPIC_PRESENCE_THR = 0.15

EXCLUDE_POS = ["PUNCT", "CCONJ", "DET", "ADP", "PRON", "PART", "SCONJ",
               "SPACE", "SYM", "NUM", "X", "AUX", "INTJ"]

EXCLUDE_TOKENS = ["-", "--", "…", "'s", "n't", "'re", "'ve", "'d", "'ll",
                  "https", "http", "see", "however", "also", "university",
                  "die", "von", "der", "den", "zur", "lo", "di", "lot",
                  "o6p", "xl", "dq", "на", "g6", "g12", "iii", "ap", "rrr", "rr",
                  "wkh", "oc", "robert", "kerala", "bäyrämova", "torigni",
                  "avranches", "dl", "……", "reproduction", "tí", "press", "walter"]

OUT_DIR = BASE_DIR / "output" / "topic_modelling"
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ──────────────────────────────────────────────────────────────────────
#  HELPER — années
# ──────────────────────────────────────────────────────────────────────

def build_year_series(df_lv, corpus_json_path):
    if META_CSV.exists():
        meta = pd.read_csv(META_CSV, encoding="utf-8-sig")
        if "year" in meta.columns and len(meta) == len(df_lv):
            return pd.Series(
                pd.to_numeric(meta["year"].values, errors="coerce"),
                index=df_lv.index,
            )
    with open(corpus_json_path, encoding="utf-8", errors="replace") as f:
        data = json.load(f)
    docs  = data if isinstance(data, list) else data.get("docs", [])
    years = []
    for entry in docs[:len(df_lv)]:
        doc = entry.get("document", entry)
        years.append(doc.get("year"))
    while len(years) < len(df_lv):
        years.append(None)
    return pd.Series(pd.to_numeric(years, errors="coerce"), index=df_lv.index)


# ──────────────────────────────────────────────────────────────────────
#  MAIN
# ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":

    # 1. Stopwords
    with open(STOPWORDS_PATH, encoding="utf-8", errors="replace") as f:
        STOPWORDS = [line.strip() for line in f if line.strip()]

    # 2. Vue lexicale — identique à 06_sweep_LDA.py
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
    df_lv["year"] = build_year_series(df_lv, CORPUS_JSON)
    print(f"{len(df_lv)} documents chargés")

    # 3. Dictionary + corpus BoW — identique à 06_sweep_LDA.py
    dictionary = corpora.Dictionary(df_lv["lemma"])
    # dictionary.filter_extremes(no_below=5)
    corpus_bow = [dictionary.doc2bow(t) for t in df_lv["lemma"]]
    print(f"Vocabulaire : {len(dictionary):,} formes | {len(corpus_bow):,} documents")

    # 4. Modèle LDA final — même seed → c_v identique au sweep
    print(f"\nEntraînement LDA : k={NUM_TOPICS}, passes={LDA_PASSES}, seed={LDA_SEED} …")
    np.random.seed(LDA_SEED)
    lda_model = LdaModel(
        corpus_bow,
        num_topics   = NUM_TOPICS,
        id2word      = dictionary,
        passes       = LDA_PASSES,
        random_state = LDA_SEED,
    )

    # Vérification de la cohérence (doit correspondre au sweep)
    cm = CoherenceModel(
        model      = lda_model,
        texts      = df_lv["lemma"].to_list(),
        dictionary = dictionary,
        coherence  = "c_v",
        processes  = 1,
    )
    coh = cm.get_coherence()
    print(f"Cohérence c_v = {coh:.4f}  (doit correspondre à la valeur du sweep pour k={NUM_TOPICS})")

    # 5. Sauvegarde du modèle
    model_dir = OUT_DIR / "lda_model"
    model_dir.mkdir(exist_ok=True)
    lda_model.save(str(model_dir / "lda.model"))
    dictionary.save(str(model_dir / "dictionary.gensim"))
    print(f"✓ Modèle sauvegardé → {model_dir}")

    # 6. Matrice gamma (documents × topics)
    print("\nMatrice gamma …")
    gamma_matrix = lda_model.get_document_topics(corpus_bow, minimum_probability=0)
    gamma_array  = np.zeros((len(corpus_bow), NUM_TOPICS), dtype=np.float64)
    for doc_idx, doc_topics in enumerate(gamma_matrix):
        for topic_id, prob in doc_topics:
            gamma_array[doc_idx, int(topic_id)] = float(prob)

    gamma_df = pd.DataFrame(gamma_array,
                            columns=[f"T{i}" for i in range(NUM_TOPICS)])
    gamma_df.index = df_lv.index
    gamma_df.to_csv(OUT_DIR / "gamma_df.csv", encoding="utf-8-sig")
    print(gamma_df)

    # 7. Matrice beta (topics × mots)
    print("\nMatrice beta …")
    beta_df = pd.DataFrame(
        lda_model.get_topics(),
        columns = [dictionary[i] for i in range(len(dictionary))],
        index   = [f"T{i}" for i in range(NUM_TOPICS)],
    )
    beta_df.to_csv(OUT_DIR / "beta_df.csv", encoding="utf-8-sig")

    # 8. Mots par topic
    print(f"\nTopics (top {TOPIC_TOPN} mots) :")
    rows_csv, lines_txt = [], [
        "TOPICS LDA", "=" * 65,
        f"k={NUM_TOPICS} | passes={LDA_PASSES} | seed={LDA_SEED} | c_v={coh:.4f}", "",
    ]
    for topic_id in range(NUM_TOPICS):
        topic_words = lda_model.get_topic_terms(topic_id, topn=TOPIC_TOPN)
        label = " / ".join(dictionary[wid] for wid, _ in topic_words[:5])
        print(f"\n  Topic {topic_id} — {label}")
        lines_txt += [f"Topic {topic_id:2d} — {label}", "-" * 50]
        for rank, (word_id, freq) in enumerate(topic_words, 1):
            word = dictionary[word_id]
            print(f"    {word:<35} {freq:.4f}")
            lines_txt.append(f"  {word:<38} {freq:.5f}")
            rows_csv.append({"topic_id": topic_id, "label": label,
                             "rang": rank, "mot": word, "probabilite": freq})
        lines_txt.append("")

    (OUT_DIR / "topics_lda.txt").write_text("\n".join(lines_txt), encoding="utf-8")
    pd.DataFrame(rows_csv).to_csv(OUT_DIR / "topics_lda.csv",
                                  index=False, encoding="utf-8-sig")

    # 9. plot_tm
    nrows = (NUM_TOPICS + 1) // 2
    plot_tm(lda_model, nwords=15, nrows=nrows, ncols=2)
    plt.savefig(str(OUT_DIR / "01_plot_tm.pdf"), format="pdf", bbox_inches="tight")
    plt.close()
    print("\n→ 01_plot_tm.pdf")

    # 10. Top documents par topic
    print("\nTop 10 documents par topic :")
    exploration_lines = ["TOP DOCUMENTS PAR TOPIC", "=" * 60, ""]
    for tid in range(NUM_TOPICS):
        col   = f"T{tid}"
        top10 = gamma_df.sort_values(by=col, ascending=False).head(10)
        exploration_lines += [f"Topic {tid}", "-" * 40]
        for rank, (idx, row) in enumerate(top10.iterrows(), 1):
            year_val = df_lv.loc[idx, "year"] if "year" in df_lv.columns else "?"
            exploration_lines.append(f"  {rank}. P={row[col]:.4f}  index={idx}  year={year_val}")
        exploration_lines.append("")
    (OUT_DIR / "top_docs_par_topic.txt").write_text(
        "\n".join(exploration_lines), encoding="utf-8")
    print("→ top_docs_par_topic.txt")

    # 11. Évolution temporelle
    if df_lv["year"].notna().sum() > 0:
        topic_cols = [f"T{i}" for i in range(NUM_TOPICS)]
        palette    = (sns.color_palette("tab10", NUM_TOPICS) if NUM_TOPICS <= 10
                      else sns.color_palette("tab20", NUM_TOPICS))

        def short_label(tid):
            words = [dictionary[wid]
                     for wid, _ in lda_model.get_topic_terms(tid, topn=3)]
            return f"T{tid} — {' / '.join(words)}"
        labels = [short_label(i) for i in range(NUM_TOPICS)]

        presence_df = (gamma_df[topic_cols] >= TOPIC_PRESENCE_THR).astype(int).copy()
        presence_df["year"] = pd.to_numeric(df_lv["year"].values, errors="coerce")
        presence_df = presence_df.dropna(subset=["year"])
        presence_df["year"] = presence_df["year"].astype(int)
        counts = presence_df.groupby("year")[topic_cols].sum()

        fig, ax = plt.subplots(figsize=(max(12, len(counts) * 0.6), 6))
        bottom = np.zeros(len(counts))
        for i, col in enumerate(topic_cols):
            ax.bar(counts.index, counts[col].values, bottom=bottom,
                   color=palette[i], label=labels[i],
                   edgecolor="white", linewidth=0.4)
            bottom += counts[col].values
        ax.set_xlabel("Année", fontsize=11)
        ax.set_ylabel(f"Nb de documents (seuil ≥ {TOPIC_PRESENCE_THR})", fontsize=11)
        ax.set_title(f"Occurrences de chaque topic par année — k={NUM_TOPICS}", fontsize=12)
        ax.legend(bbox_to_anchor=(1.01, 1), loc="upper left",
                  fontsize=8, frameon=True, title="Topics")
        ax.set_xticks(counts.index)
        ax.tick_params(axis="x", rotation=70, labelsize=8)
        ax.grid(axis="y", alpha=0.3, ls=":")
        plt.tight_layout()
        plt.savefig(str(OUT_DIR / "02_topics_par_an.pdf"),
                    format="pdf", bbox_inches="tight")
        plt.close()
        print("02_topics_par_an.pdf")

    print(f"Terminé — {NUM_TOPICS} topics | c_v = {coh:.4f}")
    print(f"Fichiers dans : {OUT_DIR.resolve()}")
