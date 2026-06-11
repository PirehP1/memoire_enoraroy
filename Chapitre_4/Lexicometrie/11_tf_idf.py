#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
  SCRIPT 11 — TF-IDF PAR DOCUMENT ET PAR ANNÉE

Calcule le TF-IDF à l'échelle du document (spécificité lexicale de
chaque texte) et à l'échelle de l'année (spécificité par période).

SORTIES
-------
  output/tfidf/
    fig_exemple_document.pdf    ← barplot top-20 lemmes d'un document
    fig_top_par_annee.pdf       ← tableau top-N lemmes par année
    tfidf_top20_par_doc.csv     ← top-20 TF-IDF par document
    tfidf_top_par_annee.csv     ← top-N TF-IDF par année
    tfidf_top_par_annee.tex     ← tableau LaTeX

STRUCTURE ATTENDUE
------------------
  <dossier du script>/
  ├── output/corpus_propre/corpus_propre.json
  ├── meta_lemmatisation.csv
  └── stopwords-en.txt

USAGE
-----
  python 11_tfidf.py
  python 11_tfidf.py --doc "titre ou mot-clé du document"

DÉPENDANCES
-----------
  pip install lexploreur scikit-learn pandas matplotlib seaborn
=======================================================================
"""

import re
import sys
import pathlib
import argparse

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import seaborn as sns

from lexploreur.corpus import *
from lexploreur.utils import *
from lexploreur.tm import *

from sklearn.feature_extraction.text import CountVectorizer, TfidfTransformer

BASE_DIR = pathlib.Path(__file__).resolve().parent

CORPUS_JSON    = BASE_DIR / "output" / "corpus_propre" / "corpus_propre.json"
STOPWORDS_PATH = BASE_DIR / "stopwords-en.txt"
META_CSV       = BASE_DIR / "meta_lemmatisation.csv"

OUT_DIR = BASE_DIR / "output" / "tfidf"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TOP_N_DOC  = 20   # lemmes affichés par document
TOP_N_YEAR = 5    # lemmes dans le tableau par année

EXCLUDE_POS    = ["PUNCT", "SPACE", "SYM", "NUM", "AUX", "X", "PROPN"]
EXCLUDE_TOKENS = ["-", "--", "…", "'s", "n't", "'re", "'ve", "'d", "'ll"]

MIN_DF = 3   # ignorer les termes présents dans < N documents/années

_CLEAN_RE = re.compile(r"^[a-z]{3,}$")   # uniquement lettres ASCII, min 3 car.


def clean_token_lists(df_lv: pd.DataFrame, col: str = "lemma",
                      stopwords: list = None) -> pd.DataFrame:
    """
    Filtre les listes de tokens dans la colonne `col` :
      - conserve uniquement les formes purement alphabétiques ASCII (a-z)
      - longueur ≥ 3 caractères
      - élimine les stopwords supplémentaires
    Supprime les apostrophes isolées, artefacts d'encodage (ñ, œ, …),
    fragments OCR et caractères de substitution.
    """
    sw_set = set(stopwords) if stopwords else set()
    df_out = df_lv.copy()
    df_out[col] = df_out[col].apply(
        lambda tokens: [
            t for t in tokens
            if _CLEAN_RE.match(t) and t not in sw_set
        ]
    )
    return df_out


def load_stopwords() -> list:
    """Charge les stopwords depuis stopwords-en.txt, ou utilise la liste intégrée."""
    if STOPWORDS_PATH.exists():
        sw = [line.strip() for line in STOPWORDS_PATH.read_text(encoding="utf-8").splitlines()
              if line.strip()]
        print(f"  Stopwords depuis {STOPWORDS_PATH.name} ({len(sw)} mots)")
        return sw
    print(f"  [AVERT] {STOPWORDS_PATH.name} introuvable — stopwords intégrés ({len(STOPWORDS_FALLBACK)} mots)")
    return STOPWORDS_FALLBACK


def build_tfidf(df_lv: pd.DataFrame, col: str = "lemma") -> tuple:
    """
    Construit DTM + TF-IDF depuis une vue lexicale lexploreur.
    """
    vectorizer = CountVectorizer(
        tokenizer=nothing, preprocessor=nothing, token_pattern=None,
        min_df=MIN_DF,
    )
    X   = vectorizer.fit_transform(df_lv[col])
    dtm = pd.DataFrame(X.toarray(), columns=vectorizer.get_feature_names_out())

    tfidf_transformer = TfidfTransformer()
    tfidf_matrix      = tfidf_transformer.fit_transform(dtm)
    tfidf_df          = pd.DataFrame(
        tfidf_matrix.toarray(),
        columns=vectorizer.get_feature_names_out(),
    )
    return dtm, tfidf_df


# ──────────────────────────────────────────────────────────────────────
#  FIGURE 1 — Barplot top-N lemmes d'un document
# ──────────────────────────────────────────────────────────────────────

def fig_document(tfidf_df: pd.DataFrame, doc_idx: int,
                 doc_label: str, n: int = TOP_N_DOC) -> plt.Figure:
    """Barplot horizontal des n lemmes TF-IDF les plus élevés pour un document."""
    row = tfidf_df.iloc[doc_idx]
    top = row.sort_values(ascending=False).head(n).sort_values()

    fig, ax = plt.subplots(figsize=(8, 6))
    colors  = sns.color_palette("Blues_d", len(top))
    bars    = ax.barh(top.index, top.values,
                      color=colors, edgecolor="white", linewidth=0.3)
    ax.bar_label(bars, fmt="%.4f", padding=4, fontsize=8, color="#333333")

    ax.set_xlabel("Score TF-IDF", fontsize=10)
    ax.set_title(
        f"Top {n} lemmes les plus spécifiques\n« {doc_label} »",
        fontsize=11, pad=12,
    )
    ax.spines[["top", "right"]].set_visible(False)
    ax.xaxis.set_major_formatter(ticker.FormatStrFormatter("%.3f"))
    plt.tight_layout()
    return fig


# ──────────────────────────────────────────────────────────────────────
#  FIGURE 2 — Tableau top-N lemmes par année
# ──────────────────────────────────────────────────────────────────────

def fig_top_year(pivot: pd.DataFrame) -> plt.Figure:
    """Tableau matplotlib : lignes = années, colonnes = Top 1/2/…/N."""
    n_rows  = len(pivot)
    fig_h   = max(3.5, n_rows * 0.45 + 1.5)
    fig, ax = plt.subplots(figsize=(9, fig_h))
    ax.axis("off")

    col_labels = list(pivot.columns)
    cell_text  = pivot.fillna("—").astype(str).values.tolist()

    tbl = ax.table(
        cellText=cell_text, colLabels=col_labels,
        cellLoc="center", loc="center",
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(9)
    tbl.scale(1.2, 1.7)

    header_color = "#2c4770"
    year_color   = "#dce6f5"
    for (r, c), cell in tbl.get_celld().items():
        cell.set_edgecolor("#cccccc")
        if r == 0:
            cell.set_facecolor(header_color)
            cell.set_text_props(color="white", fontweight="bold")
        elif c == 0:
            cell.set_facecolor(year_color)
            cell.set_text_props(fontweight="bold")
        elif r % 2 == 0:
            cell.set_facecolor("#f4f7ff")

    ax.set_title(
        f"Top {TOP_N_YEAR} lemmes (TF-IDF) par année",
        fontsize=12, pad=14, fontweight="bold",
    )
    plt.tight_layout()
    return fig


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--doc", type=str, default=None,
        help="Titre (ou début de titre) du document à illustrer. "
             "Par défaut : premier document du corpus.",
    )
    return p.parse_args()


def main():
    args = parse_args()

    print("\n" + "=" * 65)
    print("  SCRIPT 11 — TF-IDF PAR DOCUMENT ET PAR ANNÉE")
    print("=" * 65)

    if not CORPUS_JSON.exists():
        print(f"\n  [ERREUR] Corpus JSON introuvable : {CORPUS_JSON}")
        sys.exit(1)

    stopwords = load_stopwords()

    # ── 1. TF-IDF PAR DOCUMENT ───────────────────────────────────────
    print("\n── 1. lexical_view() — niveau document ───────────────────────")
    df_doc = lexical_view(
        str(CORPUS_JSON),
        feature_to_extract = "lemma",
        stopwords          = stopwords,
        lowercase          = True,
        exclude_pos        = EXCLUDE_POS,
        exclude_tokens     = EXCLUDE_TOKENS,
    )
    print(f"  {len(df_doc)} documents")
    df_doc = clean_token_lists(df_doc, col="lemma", stopwords=stopwords)

    # Récupère les titres depuis meta_lemmatisation.csv si disponible
    meta_df = pd.read_csv(META_CSV, encoding="utf-8-sig") \
              if META_CSV.exists() else pd.DataFrame()

    # ── 2. CountVectorizer + TfidfTransformer (document) ─────────────
    print("\n── 2. CountVectorizer + TfidfTransformer (document) ──────────")
    _, tfidf_doc = build_tfidf(df_doc, col="lemma")

    if not meta_df.empty and "title" in meta_df.columns:
        doc_labels = meta_df["title"].fillna(meta_df["doc_id"].astype(str)).tolist()
        doc_labels = doc_labels[:len(tfidf_doc)]
    else:
        doc_labels = [f"doc_{i}" for i in range(len(tfidf_doc))]

    tfidf_doc.index = doc_labels

    # Export top-20 par document
    top20_rows = []
    for idx, label in enumerate(doc_labels):
        row = tfidf_doc.iloc[idx]
        top = row.sort_values(ascending=False).head(TOP_N_DOC)
        for rang, (lemme, score) in enumerate(top.items(), 1):
            top20_rows.append({"document": label, "rang": rang,
                               "lemme": lemme, "tfidf": round(score, 5)})
    pd.DataFrame(top20_rows).to_csv(
        OUT_DIR / "tfidf_top20_par_doc.csv", index=False, encoding="utf-8-sig"
    )
    print(f"  → tfidf_top20_par_doc.csv  ({len(doc_labels)} documents)")

    # Choix du document à illustrer
    if args.doc:
        matches = [i for i, l in enumerate(doc_labels)
                   if args.doc.lower() in l.lower()]
        doc_idx = matches[0] if matches else 0
        if not matches:
            print(f"  [AVERT] « {args.doc} » introuvable — utilisation du premier document")
    else:
        doc_idx = 0
    doc_label = doc_labels[doc_idx]
    print(f"\n  Document illustré (index {doc_idx}) : « {doc_label} »")

    fig1 = fig_document(tfidf_doc, doc_idx, doc_label)
    fig1.savefig(str(OUT_DIR / "fig_exemple_document.pdf"),
                 format="pdf", bbox_inches="tight")
    plt.close(fig1)
    print("  → fig_exemple_document.pdf")

    # ── 3. TF-IDF PAR ANNÉE ──────────────────────────────────────────
    print("\n── 3. lexical_view(group_by='year') ──────────────────────────")
    df_year = lexical_view(
        str(CORPUS_JSON),
        feature_to_extract = "lemma",
        stopwords          = stopwords,
        lowercase          = True,
        exclude_pos        = EXCLUDE_POS,
        exclude_tokens     = EXCLUDE_TOKENS,
        group_by           = "year",
    )
    print(f"  {len(df_year)} années")
    df_year = clean_token_lists(df_year, col="lemma", stopwords=stopwords)

    print("\n── 4. CountVectorizer + TfidfTransformer (année) ─────────────")
    _, tfidf_year = build_tfidf(df_year, col="lemma")
    tfidf_year.index = df_year["year"].astype(str)

    # Top-N lemmes par année
    top_year_rows = []
    for year_str, row in tfidf_year.iterrows():
        top = row.sort_values(ascending=False).head(TOP_N_YEAR)
        for rang, (lemme, score) in enumerate(top.items(), 1):
            top_year_rows.append({"annee": year_str, "rang": rang,
                                  "lemme": lemme, "tfidf": round(score, 5)})
    top_year_df = pd.DataFrame(top_year_rows)
    top_year_df.to_csv(OUT_DIR / "tfidf_top_par_annee.csv",
                       index=False, encoding="utf-8-sig")
    print("  → tfidf_top_par_annee.csv")

    # Pivot pour la figure tableau
    top_year_df["rang_label"] = top_year_df["rang"].apply(lambda r: f"Top {r}")
    pivot = (top_year_df
             .pivot(index="annee", columns="rang_label", values="lemme")
             .reset_index()
             .rename(columns={"annee": "Année"}))
    pivot.columns.name = None
    pivot = pivot.sort_values("Année").reset_index(drop=True)

    # Export LaTeX
    latex_table = pivot.to_latex(
        index=False,
        escape=True,
        column_format="l" + "c" * TOP_N_YEAR,
    )
    latex_table = (
        "\\begin{table}[h]\n\\centering\n"
        + latex_table
        + "\\caption{Top " + str(TOP_N_YEAR) + " des lemmes (TF-IDF) par année}\n"
        "\\label{tab:tfidf_top_annee}\n"
        "\\end{table}\n"
    )
    (OUT_DIR / "tfidf_top_par_annee.tex").write_text(latex_table, encoding="utf-8")
    print("  → tfidf_top_par_annee.tex")

    print("\n  Aperçu du tableau :")
    print(pivot.to_string(index=False))

    fig2 = fig_top_year(pivot)
    fig2.savefig(str(OUT_DIR / "fig_top_par_annee.pdf"),
                 format="pdf", bbox_inches="tight")
    plt.close(fig2)
    print("\n  → fig_top_par_annee.pdf")

    print(f"  Fichiers produits :")
    print(f"    fig_exemple_document.pdf   — barplot doc « {doc_label[:50]} »")
    print(f"    fig_top_par_annee.pdf      — tableau top-{TOP_N_YEAR} lemmes × années")
    print(f"    tfidf_top20_par_doc.csv    — top-{TOP_N_DOC} TF-IDF par document")
    print(f"    tfidf_top_par_annee.csv    — top-{TOP_N_YEAR} TF-IDF par année")
    print(f"    tfidf_top_par_annee.tex    — tableau LaTeX")


if __name__ == "__main__":
    main()
