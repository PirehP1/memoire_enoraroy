
"""
TABLEAU DE CONTINGENCE ANNUEL  LEMMES × ANNÉES
  Source : corpus_propre.json

Lit le corpus JSON produit par lexploreur (corpus_propre.json),
construit un tableau de contingence LEMMES × ANNÉES (occurrences brutes),
puis produit deux versions dérivées :
  - profils lignes normalisés (fréquences relatives par lemme)
  - tableau centré-réduit (z-score par ligne/lemme)

Ce script est complémentaire de 05_tab_cont_lemme_annee.py :
là où le script 03 agrège par période (Jenks), celui-ci conserve la
granularité annuelle, ce qui permet une analyse fine de l'évolution
lexicale année par année.

Filtres appliqués (identiques à 03_tableau_contingence_lemmes_annees.py) :
  • POS exclus    : EXCLUDE_POS (cf. configuration)
  • Stopwords     : STOPWORDS   (cf. configuration)
  • Longueur min. : 3 caractères, alphabétique uniquement
  • Fréquence min.: --min-freq occurrences dans le corpus entier
  • Sélection top : --top-n lemmes les plus fréquents

SORTIES  (--output, défaut : output/contingency_annees/)
---------------------------------------------------------
  contingency_raw.csv        — occurrences brutes   (lemmes × années)
  contingency_norm.csv       — fréquences relatives  (profils lignes)
  corpus_stats.csv           — statistiques par année (tokens, types…)

USAGE
-----
  python 03bis_tableau_contingence_annees.py corpus_propre.json
  python 03bis_tableau_contingence_annees.py corpus_propre.json \\
      --year-min 1980 --year-max 2020 \\
      --min-freq 3 --top-n 300 \\
      --output output/contingency_annees

DÉPENDANCES
-----------
  pip install pandas numpy tqdm
=======================================================================
"""

import argparse
import json
import pathlib
import sys
from collections import Counter, defaultdict

import numpy as np
import pandas as pd
from tqdm import tqdm

# POS à exclure — identique à 03_tableau_contingence_lemmes_annees.py
EXCLUDE_POS = {
    "PUNCT", "CCONJ", "DET", "ADP", "PRON",
    "PART", "SCONJ", "SPACE", "SYM", "NUM", "X",
    "AUX", "INTJ",
}
STOPWORDS = {"https", "see", "den", "http", "however", "zur", "also"}

def load_corpus(json_path: pathlib.Path, year_min: int, year_max: int) -> list:
    """
    Lit le JSON lexploreur.
    Chaque entrée contient au minimum :
      "year"             — année de publication
      "lexical_features" — liste de dicts {"lemma": str, "pos": str, ...}
      "n_tokens"         — nombre de tokens (optionnel)
    Supporte aussi le format {"document": {...}}.
    """
    print(f"\n── 1. Chargement : {json_path.name}")
    with open(json_path, encoding="utf-8") as f:
        raw = json.load(f)

    docs, skipped = [], 0
    for entry in tqdm(raw, desc="  Parsing"):
        d = entry.get("document", entry) if isinstance(entry, dict) else entry

        try:
            year = int(float(d.get("year", "nan")))
        except (ValueError, TypeError):
            skipped += 1
            continue

        if not (year_min <= year <= year_max):
            skipped += 1
            continue

        lf = d.get("lexical_features", [])
        if not lf:
            skipped += 1
            continue

        docs.append({
            "year"            : year,
            "n_tokens"        : int(d.get("n_tokens", len(lf))),
            "lexical_features": lf,
        })

    print(f"  → {len(docs):,} documents retenus  ({skipped} écartés)")
    return docs


def _keep_token(t: dict) -> str | None:
    """
    Retourne le lemme nettoyé si le token doit être conservé, sinon None.
    Critères identiques à 03_tableau_contingence_lemmes_annees.py :
      - POS non exclu
      - alphabétique uniquement
      - longueur ≥ 3
      - absent des STOPWORDS
    """
    pos   = t.get("pos", "")
    lemma = t.get("lemma", "").lower().strip()

    if pos in EXCLUDE_POS:
        return None
    if not lemma.isalpha() or len(lemma) < 3:
        return None
    if lemma in STOPWORDS:
        return None
    return lemma

def compute_freq_by_year(docs: list) -> tuple[dict, Counter]:
    """
    Calcule les fréquences de lemmes par année.
    Retourne :
      by_year — dict {année (int): Counter}
      glob    — Counter global (toutes années confondues)
    """
    by_year: dict[int, Counter] = defaultdict(Counter)
    glob: Counter = Counter()

    for doc in tqdm(docs, desc="  Fréquences par année"):
        year = doc["year"]
        for t in doc["lexical_features"]:
            lem = _keep_token(t)
            if lem is None:
                continue
            by_year[year][lem] += 1
            glob[lem]          += 1

    n_hap = sum(1 for f in glob.values() if f == 1)
    print(f"  Vocabulaire filtré : {len(glob):,} lemmes  (hapax : {n_hap:,})")
    return dict(by_year), glob


def build_contingency(by_year: dict, glob: Counter,
                      min_freq: int, top_n: int) -> pd.DataFrame:
    """
    Construit le tableau de contingence lemmes × années.
    Lignes   = lemmes (triés par fréquence globale décroissante).
    Colonnes = années (triées chronologiquement).
    Applique les filtres min_freq et top_n.
    Les lignes dont la somme est nulle sont supprimées.
    """
    vocab = [w for w, f in glob.most_common() if f >= min_freq][:top_n]
    print(f"  Lemmes retenus : {len(vocab):,}  "
          f"(fréq. ≥ {min_freq}, top {top_n})")

    years_sorted = sorted(by_year.keys())

    rows = {}
    for y in years_sorted:
        cnt = by_year.get(y, Counter())
        rows[y] = {w: cnt.get(w, 0) for w in vocab}

    df = pd.DataFrame(rows, index=vocab)
    df.index.name   = "lemme"
    df.columns.name = "annee"
    df = df.loc[df.sum(axis=1) > 0, :]

    print(f"  Tableau final : {df.shape[0]:,} lemmes × {df.shape[1]} années")
    print(f"  Total occurrences : {df.values.sum():,}")
    return df

def compute_stats(df: pd.DataFrame, docs: list) -> pd.DataFrame:
    """Produit un tableau de statistiques descriptives par année."""
    doc_count = Counter(d["year"] for d in docs)

    rows = []
    for year in df.columns:
        serie  = df[year]
        total  = int(serie.sum())
        n_dist = int((serie > 0).sum())
        hapax  = int((serie == 1).sum())
        top3   = serie.sort_values(ascending=False).head(3)
        rows.append({
            "annee"            : year,
            "n_documents"      : doc_count.get(year, 0),
            "occurrences_total": total,
            "lemmes_distincts" : n_dist,
            "hapax"            : hapax,
            "richesse_%"       : round(100 * n_dist / max(total, 1), 2),
            "top1_lemme"       : top3.index[0]     if len(top3) > 0 else "",
            "top1_freq"        : int(top3.iloc[0]) if len(top3) > 0 else 0,
            "top2_lemme"       : top3.index[1]     if len(top3) > 1 else "",
            "top2_freq"        : int(top3.iloc[1]) if len(top3) > 1 else 0,
            "top3_lemme"       : top3.index[2]     if len(top3) > 2 else "",
            "top3_freq"        : int(top3.iloc[2]) if len(top3) > 2 else 0,
        })
    return pd.DataFrame(rows).set_index("annee")


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Tableau de contingence LEMMES × ANNÉES avec centrage-réduction "
            "(z-score par ligne/lemme)."
        )
    )
    parser.add_argument("corpus",
        help="Chemin vers corpus_propre.json.")
    parser.add_argument("--year-min", type=int, default=1975, dest="year_min",
        help="Première année à inclure (défaut : 1975).")
    parser.add_argument("--year-max", type=int, default=2025, dest="year_max",
        help="Dernière année à inclure (défaut : 2025).")
    parser.add_argument("--min-freq", type=int, default=2, dest="min_freq",
        help="Fréquence minimale globale d'un lemme (défaut : 2).")
    parser.add_argument("--top-n", type=int, default=500, dest="top_n",
        help="Nombre max de lemmes, triés par fréquence décroissante "
             "(défaut : 500).")
    parser.add_argument("--output", default="output/contingency_annees",
        help="Dossier de sortie (défaut : output/contingency_annees/).")
    args = parser.parse_args()

    corpus_path = pathlib.Path(args.corpus)
    out_dir     = pathlib.Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not corpus_path.exists():
        print(f"\n[ERREUR] Corpus JSON introuvable : {corpus_path}")
        print("Lancez d'abord : python 01bis_construction_corpus_propre.py")
        sys.exit(1)

    print(f"  Corpus      : {corpus_path}")
    print(f"  Années      : {args.year_min}–{args.year_max}")
    print(f"  Min freq    : {args.min_freq}  |  Top lemmes : {args.top_n}")
    print(f"  POS exclus  : {sorted(EXCLUDE_POS)}")
    print(f"  Stopwords   : {len(STOPWORDS)} mots")
    print(f"  Sortie      : {out_dir.resolve()}")

    # ── 1. Chargement ────────────────────────────────────────────────
    docs = load_corpus(corpus_path, args.year_min, args.year_max)

    print("\n── 2. Fréquences de lemmes par année ─────────────────────")
    by_year, glob = compute_freq_by_year(docs)

    print("\n── 3. Tableau de contingence (brut) ──────────────────────")
    df_raw = build_contingency(by_year, glob, args.min_freq, args.top_n)

    print("\n── 4. Normalisation par ligne (fréquences relatives) ─────")
    df_norm = df_raw.div(df_raw.sum(axis=1), axis=0).round(6)
    print(f"  Somme de chaque ligne (lemme) ≈ 1.0  ✓")

    print("\n── 6. Statistiques par année ─────────────────────────────")
    stats_df = compute_stats(df_raw, docs)
    print(stats_df.to_string())

    print("\n── 7. Exports CSV ────────────────────────────────────────")

    raw_path  = out_dir / "contingency_raw.csv"
    norm_path = out_dir / "contingency_norm.csv"
    stat_path = out_dir / "corpus_stats.csv"

    df_raw.to_csv(raw_path,  encoding="utf-8-sig")
    print(f"  → {raw_path.name}   "
          f"({df_raw.shape[0]:,} lemmes × {df_raw.shape[1]} années, entiers)")

    df_norm.to_csv(norm_path, encoding="utf-8-sig")
    print(f"  → {norm_path.name}  "
          f"({df_norm.shape[0]:,} lemmes × {df_norm.shape[1]} années, fréq. rel.)")

    stats_df.to_csv(stat_path, encoding="utf-8-sig")
    print(f"  → {stat_path.name}")

    print("\n── Aperçu : top 10 lemmes les plus fréquents (brut) ─────")
    top10 = df_raw.sum(axis=1).sort_values(ascending=False).head(10).index
    print(df_raw.loc[top10].to_string())

    print(f"  ✓  Terminé → {out_dir.resolve()}")
    for fp in sorted(out_dir.glob("*.csv")):
        size = fp.stat().st_size
        unit = "Ko" if size < 1_000_000 else "Mo"
        val  = size // 1024 if size < 1_000_000 else size // (1024 * 1024)
        print(f"    {fp.name:<40} {val:>5} {unit}")

if __name__ == "__main__":
    main()
