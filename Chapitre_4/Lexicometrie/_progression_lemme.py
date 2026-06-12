"""
Analyse la distribution temporelle de lemmes cibles dans le corpus

USAGE
-----
  python progression_lemme_cible.py
  python progression_lemme_cible.py --corpus mon_corpus.json
  python progression_lemme_cible.py --plot_type density
  python progression_lemme_cible.py --plot_type frequency
  python progression_lemme_cible.py --plot_type both

SORTIE
------
  output/progression_temporelle/
      frequency_year.pdf
      density_year.pdf
      frequences_par_annee.csv

DÉPENDANCES
-----------
  pip install pandas matplotlib seaborn lexploreur
=======================================================================
"""

import argparse
import json
import pathlib
import sys
from collections import defaultdict
from unittest.mock import patch

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from lexploreur.description import plot_feature_distrib


CORPUS_PATH = pathlib.Path("output") / "corpus_propre" / "corpus_propre.json"

TARGET_LEMMAS = ["barbarian", "barbarians"]

OUTPUT_DIR = pathlib.Path("output") / "progression_temporelle"

def load_corpus(path: str) -> list:
    """Charge le corpus JSON (liste de documents ou objet racine)."""
    p = pathlib.Path(path)
    if not p.exists():
        print(f"  [ERREUR] Fichier introuvable : {path}")
        sys.exit(1)

    print(f"  Chargement de {p.name} …", end=" ", flush=True)
    with open(p, encoding="utf-8", errors="replace") as f:
        data = json.load(f)

    if isinstance(data, list):
        docs = data
    elif isinstance(data, dict):
        docs = data.get("documents", list(data.values()))
    else:
        print("[ERREUR] Format JSON non reconnu.")
        sys.exit(1)

    print(f"{len(docs):,} documents chargés")
    return docs


def build_corpus_and_dtm(docs: list, targets: list):
    """
    Construit deux DataFrames alignés (même index = un document par ligne) :

      corpus_df  — métadonnées : doc_id, year
      dtm_df     — occurrences des lemmes cibles + colonne "_other_"
                   (_other_ = total_tokens – somme des lemmes cibles)
                   → dtm_df.sum(axis=1) == total_tokens du document

    La colonne "_other_" est indispensable pour que plot_feature_distrib
    en mode "density" divise par le bon dénominateur (total du vocabulaire).
    """
    targets_lower = {t.lower() for t in targets}
    corpus_rows   = []
    dtm_rows      = []
    skipped       = 0

    for entry in docs:
        doc  = entry.get("document", entry) if isinstance(entry, dict) else {}
        year = doc.get("year")

        if year is None:
            skipped += 1
            continue
        try:
            year = int(year)
        except (ValueError, TypeError):
            skipped += 1
            continue

        # Comptage des tokens
        counts  = defaultdict(int)
        total   = 0
        for feat in doc.get("lexical_features", []):
            lemma = feat.get("lemma", "")
            if isinstance(lemma, str):
                total += 1
                lem_low = lemma.lower()
                if lem_low in targets_lower:
                    counts[lem_low] += 1

        corpus_rows.append({
            "doc_id": doc.get("doc_id", ""),
            "year"  : year,
        })

        # Ligne DTM : une colonne par lemme cible + "_other_"
        target_sum = sum(counts[t] for t in targets_lower)
        row = {t: counts[t] for t in targets_lower}
        row["_other_"] = max(0, total - target_sum)
        dtm_rows.append(row)

    if skipped:
        print(f"  [INFO] {skipped} documents sans année ignorés")

    corpus_df = pd.DataFrame(corpus_rows).reset_index(drop=True)
    dtm_df    = pd.DataFrame(dtm_rows,
                              columns=list(targets_lower) + ["_other_"]
                             ).reset_index(drop=True)

    print(f"  {len(corpus_df):,} documents  |  "
          f"{len(corpus_df['year'].unique())} années distinctes  |  "
          f"tokens_total = {dtm_df.sum().sum():,}")

    return corpus_df, dtm_df

def _call_and_save(pdf_path: pathlib.Path,
                   corpus_df, dtm_df, targets, part, plot_type,
                   figsize=(16, 6)):
    """
    Appelle plot_feature_distrib et remplace plt.show() par une
    sauvegarde PDF.  La fonction modifie dtm et features en place,
    on passe donc des copies.
    """
    dtm_copy      = dtm_df.copy()
    features_copy = list(targets)        # liste mutable, copiée

    saved = []

    def _save_instead_of_show():
        fig = plt.gcf()
        fig.set_size_inches(*figsize)
        fig.set_facecolor("white")
        # Amélioration cosmétique de l'axe X
        ax = plt.gca()
        ax.tick_params(axis="x", rotation=70, labelsize=8)
        plt.tight_layout()
        plt.savefig(str(pdf_path), format="pdf", bbox_inches="tight", dpi=200)
        plt.close()
        saved.append(True)

    with patch("matplotlib.pyplot.show", _save_instead_of_show):
        plot_feature_distrib(corpus_df, dtm_copy, features_copy, part, plot_type)

    if saved:
        print(f"  → {pdf_path.name}")
    else:
        print(f"  [AVERTISSEMENT] plot_feature_distrib n'a pas appelé plt.show()")


def export_csv(corpus_df, dtm_df, targets, out_dir):
    """Exporte les fréquences absolues et relatives par année en CSV."""
    merged = corpus_df[["year"]].copy()
    for t in targets:
        merged[f"abs_{t}"] = dtm_df[t]

    merged["total_tokens"] = dtm_df.sum(axis=1)  # inclut _other_
    grouped = merged.groupby("year")

    agg = grouped[[f"abs_{t}" for t in targets]].sum()
    agg["total_tokens"] = grouped["total_tokens"].sum()
    agg["n_docs"]       = grouped["year"].count()

    for t in targets:
        agg[f"pmw_{t}"] = (agg[f"abs_{t}"] / agg["total_tokens"] * 1_000_000
                           ).round(2)

    csv_path = out_dir / "frequences_par_annee.csv"
    agg.to_csv(str(csv_path), encoding="utf-8-sig")
    print(f"  → {csv_path.name}")
    return agg


def parse_args():
    p = argparse.ArgumentParser(
        description="Progression temporelle de lemmes cibles (lexploreur)"
    )
    p.add_argument("--corpus", default=CORPUS_PATH,
                   help="Chemin vers corpus_propre.json")
    p.add_argument("--output", default=str(OUTPUT_DIR),
                   help="Dossier de sortie")
    p.add_argument("--lemmas", nargs="+", default=TARGET_LEMMAS,
                   help="Lemmes cibles (ex: --lemmas jew jews islam)")
    p.add_argument("--plot_type", default="both",
                   choices=["frequency", "density", "both"],
                   help="Type de graphique lexploreur (défaut: both)")
    return p.parse_args()


def main():
    args    = parse_args()
    targets = [t.lower() for t in args.lemmas]
    out_dir = pathlib.Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"  Corpus      : {args.corpus}")
    print(f"  Lemmes      : {targets}")
    print(f"  Plot type   : {args.plot_type}")
    print(f"  Sortie      : {out_dir.resolve()}")
    print()

    docs = load_corpus(args.corpus)

    print("\n  Construction du corpus DataFrame et de la DTM…")
    corpus_df, dtm_df = build_corpus_and_dtm(docs, targets)

    total_tokens = dtm_df.sum().sum()
    for t in targets:
        n   = int(dtm_df[t].sum())
        pmw = n / total_tokens * 1_000_000 if total_tokens else 0
        print(f"    {t:<12} : {n:>6,} occ.  ({pmw:.1f} pmw)")

    print("\n  Export CSV :")
    export_csv(corpus_df, dtm_df, targets, out_dir)

    print("\n  Génération des figures (lexploreur.description) :")

    plot_types = (
        ["frequency", "density"] if args.plot_type == "both"
        else [args.plot_type]
    )

    for pt in plot_types:
        pdf_path = out_dir / f"{pt}_year.pdf"
        _call_and_save(
            pdf_path   = pdf_path,
            corpus_df  = corpus_df,
            dtm_df     = dtm_df,
            targets    = targets,
            part       = "year",
            plot_type  = pt,
            figsize    = (16, 6),
        )


if __name__ == "__main__":
    main()
