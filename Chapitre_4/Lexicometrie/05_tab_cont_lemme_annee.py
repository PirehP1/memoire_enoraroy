"""

Ce script découpe le corpus en périodes homogènes par la méthode de
Jenks (Natural Breaks) appliquée aux volumes cumulés de tokens par
année, puis construit le tableau de contingence lemmes × périodes
utilisé pour les analyses ultérieures (spécificités, AFC, etc.).
il découpe le corpus pour obtenir des périodes contenant approximativement des masses documentaires comparables.

Le nombre de périodes K est déterminé automatiquement par la règle
de Sturges appliquée au nombre d'années non vides du corpus.

Une année supplémentaire (--supp-year) peut être spécifiée : elle
est exclue du calcul Jenks et des décomptes de fréquences, et
signalée dans le mapping par le flag is_supp=True.

SORTIES  (--output, défaut : output/jenks_contingency/)
---------------------------------------------------------
  jenks_decoupage.pdf          — graphe de découpage Jenks
  jenks_periodes.csv           — mapping année → période (+ flag is_supp)
  contingency_table.csv        — tableau brut (occurrences)
  contingency_table_norm.csv   — profils lignes (fréquences relatives
                                  de chaque lemme par période)

USAGE
-----
  python 03_tableau_contingence_lemmes_annees.py corpus_propre.json
  python 03_tableau_contingence_lemmes_annees.py corpus_propre.json \\
      --year-min 1980 --year-max 2020 \\
      --min-freq 3 --top-n 300 \\
      --supp-year 2025 \\
      --output output/jenks_contingency

DÉPENDANCES
-----------
  pip install jenkspy pandas numpy matplotlib tqdm

Note : le tableau de contingence est ensuite analysé sur le site
http://analyse.univ-paris1.fr/

"""

import argparse
import json
import pathlib
import sys
from collections import Counter, defaultdict
from math import log10

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from tqdm import tqdm

try:
    import jenkspy
except ImportError:
    print("[ERREUR] Installez jenkspy : pip install jenkspy")
    sys.exit(1)


# ──────────────────────────────────────────────────────────────────────
# CONSTANTES (filtres lexicaux — non exposés en CLI)
# ──────────────────────────────────────────────────────────────────────

# POS à exclure (mots grammaticaux, ponctuation, etc.)
EXCLUDE_POS = {
    "PUNCT", "CCONJ", "DET", "ADP", "PRON",
    "PART", "SCONJ", "SPACE", "SYM", "NUM", "X",
    "AUX", "INTJ",
}

STOPWORDS = {"https", "see", "den", "http", "however", "zur", "also"}


def load_corpus(json_path: pathlib.Path, year_min: int, year_max: int) -> list:
    print(f"\n── 1. Chargement de {json_path.name}")
    with open(json_path, encoding="utf-8") as f:
        raw = json.load(f)

    docs, skipped = [], 0
    for entry in tqdm(raw, desc="  Parsing"):
        # Supporte les formats {"document": {...}} et directement {...}
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


def tokens_by_year(docs: list, year_min: int, year_max: int,
                   supp_year: int | None) -> pd.Series:
    """
    Calcule le nombre de tokens par année en excluant supp_year du décompte.
    Les années sans document sont remplies à 0 pour un axe continu.
    """
    counter: Counter = Counter()
    for d in docs:
        if d["year"] == supp_year:
            continue
        counter[d["year"]] += d["n_tokens"]

    for y in range(year_min, year_max + 1):
        counter.setdefault(y, 0)

    s = pd.Series(dict(counter)).sort_index()
    s.index.name, s.name = "year", "n_tokens"
    if supp_year is not None:
        print(f"  Année supplémentaire {supp_year} → tokens forcés à 0 (hors Jenks)")
    return s


def sturges_k(series: pd.Series) -> int:
    """Détermine K par la règle de Sturges sur les années non vides."""
    n = int((series > 0).sum())
    k = max(2, round(1 + 3.22 * log10(max(n, 2))))
    print(f"  Années non vides : {n}  →  K = {k} (règle de Sturges)")
    return k


def jenks_periodize(series: pd.Series, k: int) -> tuple[dict, list]:
    """
    Applique l'algo Jenks sur les volumes CUMULÉS de tokens par année.
    Retourne :
      y2p    — dict {année: label_période}
      labels — liste ordonnée des labels de périodes
    """
    years = series.index.tolist()
    cum   = np.cumsum(series.values).astype(float)

    breaks    = jenkspy.jenks_breaks(cum.tolist(), n_classes=k)
    frontiers = []
    for thr in breaks[1:-1]:
        for i, cv in enumerate(cum):
            if cv >= thr:
                frontiers.append(years[i])
                break
    frontiers = sorted(set(frontiers))

    bounds = [years[0]] + frontiers + [years[-1] + 1]
    ranges = [(bounds[i], bounds[i + 1] - 1) for i in range(len(bounds) - 1)]
    labels = [f"{s}–{e}" for s, e in ranges]
    y2p    = {y: lbl for (s, e), lbl in zip(ranges, labels) for y in range(s, e + 1)}

    # Tableau de périodisation
    total = cum[-1]
    print(f"\n  {'Période':<16} {'Années':>6}  {'Tokens':>10}  {'%':>6}")
    print("  " + "─" * 44)
    for (s, e), lbl in zip(ranges, labels):
        tok  = sum(series.get(y, 0) for y in range(s, e + 1))
        n_yr = e - s + 1
        print(f"  {lbl:<16} {n_yr:>6}  {tok:>10,}  {100*tok/max(total,1):>5.1f}%")

    return y2p, labels


# GRAPHE DE DÉCOUPAGE JENKS
def plot_jenks(series: pd.Series, y2p: dict, labels: list,
               out_path: pathlib.Path, supp_year: int | None) -> None:
    """
    Graphe en deux panneaux :
      Haut — tokens bruts par année (barres colorées par période) + frontières
      Bas  — tokens cumulés + points de rupture Jenks
    L'année supplémentaire est marquée d'une étoile rouge si elle est définie.
    """
    all_years = sorted(series.index)
    frontiers = []
    prev_p    = y2p.get(all_years[0])
    for y in all_years[1:]:
        curr_p = y2p.get(y)
        if curr_p != prev_p:
            frontiers.append(y)
            prev_p = curr_p

    cum = np.cumsum(series.values)

    # Palette de couleurs par période
    n_periods   = len(labels)
    period_cmap = matplotlib.colormaps["tab10"].resampled(n_periods)
    lbl_to_col  = {lbl: period_cmap(i) for i, lbl in enumerate(labels)}
    bar_colors  = [lbl_to_col.get(y2p.get(y, ""), "#aaaaaa") for y in all_years]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 9), sharex=True,
                                   gridspec_kw={"height_ratios": [3, 2]})

    # ── Panneau 1 : tokens par année ────────────────────────────────
    ax1.bar(all_years, series.values, color=bar_colors,
            width=0.8, alpha=0.82, edgecolor="white", linewidth=0.3)

    for f in frontiers:
        ax1.axvline(f - 0.5, color="#333", lw=1.5, ls="--", alpha=0.7)

    # Étiquettes de période au centre de chaque segment
    bounds   = [all_years[0]] + frontiers + [all_years[-1] + 1]
    ylim_top = ax1.get_ylim()[1]
    for i, lbl in enumerate(labels):
        mid = (bounds[i] + bounds[i + 1] - 1) / 2
        ax1.text(mid, ylim_top * 0.97, lbl,
                 ha="center", va="top", fontsize=8.5,
                 color=period_cmap(i), fontweight="bold",
                 bbox=dict(fc="white", ec=period_cmap(i), alpha=0.8, pad=2))

    if supp_year is not None and supp_year in series.index:
        ax1.axvline(supp_year, color="#d62728", lw=2, ls=":", alpha=0.9)
        ax1.scatter([supp_year], [0], marker="*", s=220,
                    color="#d62728", zorder=6,
                    label=f"{supp_year} (supplémentaire)")
        ax1.legend(fontsize=9, loc="upper left")

    ax1.set_ylabel("Tokens par année", fontsize=10)
    supp_label = f"  |  année supplémentaire : {supp_year}" if supp_year else ""
    ax1.set_title(
        f"Périodisation Jenks (K = {n_periods}) — volumétrie du corpus\n"
        f"{series.index.min()}–{series.index.max()}{supp_label}",
        fontsize=12,
    )
    ax1.grid(axis="y", alpha=0.25, ls=":")

    # ── Panneau 2 : tokens cumulés + ruptures ───────────────────────
    ax2.plot(all_years, cum, color="#2c7bb6", lw=2.2, zorder=3)
    ax2.fill_between(all_years, cum, alpha=0.15, color="#2c7bb6")
    for f in frontiers:
        idx = all_years.index(f)
        ax2.axvline(f - 0.5, color="#333", lw=1.5, ls="--", alpha=0.7)
        ax2.scatter([f], [cum[idx]], s=80, color="#d62728",
                    zorder=5, edgecolors="white", linewidths=0.8)
    if supp_year is not None and supp_year in all_years:
        ax2.axvline(supp_year, color="#d62728", lw=2, ls=":", alpha=0.9)

    ax2.set_xlabel("Année", fontsize=10)
    ax2.set_ylabel("Tokens cumulés", fontsize=10)
    ax2.grid(alpha=0.25, ls=":")
    ax2.yaxis.set_major_formatter(
        plt.FuncFormatter(lambda x, _: f"{int(x):,}")
    )

    plt.tight_layout()
    plt.savefig(str(out_path), format="pdf", bbox_inches="tight")
    plt.close()
    print(f"  → {out_path.name}")


# ──────────────────────────────────────────────────────────────────────
# 5. FRÉQUENCES DE LEMMES PAR PÉRIODE
# ──────────────────────────────────────────────────────────────────────

def _keep_token(t: dict) -> str | None:
    """Retourne le lemme filtré, ou None si le token doit être ignoré."""
    pos   = t.get("pos", "")
    lemma = t.get("lemma", "").lower().strip()
    if pos in EXCLUDE_POS:
        return None
    if not lemma.isalpha() or len(lemma) < 3:
        return None
    if lemma in STOPWORDS:
        return None
    return lemma


def compute_freq_by_period(docs: list, y2p: dict,
                           supp_year: int | None) -> tuple[dict, Counter]:
    """
    Calcule les fréquences de lemmes par période en excluant supp_year.
    Retourne :
      by_period — dict {période: Counter}
      glob      — Counter global (toutes périodes confondues)
    """
    by_period = defaultdict(Counter)
    glob      = Counter()

    for doc in tqdm(docs, desc="  Fréquences par période"):
        if doc["year"] == supp_year:
            continue

        period = y2p.get(doc["year"])
        if period is None:
            continue

        for t in doc["lexical_features"]:
            lem = _keep_token(t)
            if lem is None:
                continue
            by_period[period][lem] += 1
            glob[lem]              += 1

    n_hap = sum(1 for f in glob.values() if f == 1)
    print(f"  Vocabulaire filtré : {len(glob):,} lemmes  (hapax : {n_hap:,})")
    return dict(by_period), glob


def build_contingency(by_period: dict, period_labels: list,
                      glob: Counter, min_freq: int,
                      top_n: int) -> pd.DataFrame:
    """
    Construit le tableau de contingence lemmes × périodes.

    Sélection du vocabulaire :
      - fréquence globale ≥ min_freq
      - top top_n lemmes triés par fréquence décroissante
    Les lignes dont la somme est nulle sont supprimées.
    """
    vocab = [w for w, f in glob.most_common() if f >= min_freq][:top_n]
    print(f"  Lemmes retenus : {len(vocab):,}  (freq ≥ {min_freq}, top {top_n})")

    rows = {}
    for p in period_labels:
        cnt = by_period.get(p, Counter())
        rows[p] = {w: cnt.get(w, 0) for w in vocab}

    df = pd.DataFrame(rows, index=vocab)
    df.index.name = "lemme"
    df = df.loc[df.sum(axis=1) > 0, :]   # supprime les lignes à 0

    print(f"  Tableau final : {df.shape[0]:,} lemmes × {df.shape[1]} périodes")
    print(f"  Total occurrences : {df.values.sum():,}")
    return df


# ──────────────────────────────────────────────────────────────────────
# PROGRAMME PRINCIPAL
# ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Périodisation Jenks (Natural Breaks) + tableau de contingence "
            "lemmes × périodes."
        )
    )
    parser.add_argument("corpus",
        help="Chemin vers corpus_propre.json.")
    parser.add_argument("--year-min", type=int, default=1975, dest="year_min",
        help="Première année à inclure (défaut : 1975).")
    parser.add_argument("--year-max", type=int, default=2025, dest="year_max",
        help="Dernière année à inclure (défaut : 2025).")
    parser.add_argument("--min-freq", type=int, default=2, dest="min_freq",
        help="Fréquence minimale d'un lemme pour figurer dans le tableau "
             "(défaut : 2).")
    parser.add_argument("--top-n", type=int, default=500, dest="top_n",
        help="Nombre max de lemmes dans le tableau, triés par fréquence "
             "décroissante (défaut : 500).")
    parser.add_argument("--supp-year", type=int, default=None, dest="supp_year",
        help="Année supplémentaire exclue de Jenks et des fréquences, "
             "signalée dans le CSV par is_supp=True (optionnel).")
    parser.add_argument("--output", default="output/jenks_contingency",
        help="Dossier de sortie (défaut : output/jenks_contingency/).")
    args = parser.parse_args()

    corpus_path = pathlib.Path(args.corpus)
    out_dir     = pathlib.Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not corpus_path.exists():
        print(f"\n[ERREUR] Corpus JSON introuvable : {corpus_path}")
        print("Lancez d'abord : python 01bis_construction_corpus_propre.py")
        sys.exit(1)

    print("  PÉRIODISATION JENKS + TABLEAU DE CONTINGENCE")
    print(f"  Corpus      : {corpus_path}")
    print(f"  Années      : {args.year_min}–{args.year_max}")
    print(f"  Année supp. : {args.supp_year if args.supp_year is not None else '—'}")
    print(f"  Min freq    : {args.min_freq}  |  Top lemmes : {args.top_n}")
    print(f"  Sortie      : {out_dir.resolve()}")

    docs = load_corpus(corpus_path, args.year_min, args.year_max)

    print("\n── 2. Volumétrie par année ───────────────────────────────")
    series = tokens_by_year(docs, args.year_min, args.year_max, args.supp_year)

    print("\n── 3. Périodisation Jenks ────────────────────────────────")
    k           = sturges_k(series)
    y2p, labels = jenks_periodize(series, k)

    # Sauvegarde du mapping année → période
    # is_supp=True signale l'année supplémentaire sans l'exclure du mapping
    rows_jenks = [
        {"annee": y, "periode": p, "is_supp": (y == args.supp_year)}
        for y, p in sorted(y2p.items())
    ]
    (
        pd.DataFrame(rows_jenks)
        .sort_values("annee")
        .to_csv(out_dir / "jenks_periodes.csv", index=False, encoding="utf-8-sig")
    )
    print(f"  → jenks_periodes.csv")

    # ── 4. Graphe de découpage ─────────────────────────────────────────
    print("\n── 4. Graphe de découpage ────────────────────────────────")
    plot_jenks(series, y2p, labels,
               out_dir / "jenks_decoupage.pdf", args.supp_year)

    # ── 5. Fréquences par période ──────────────────────────────────────
    print("\n── 5. Fréquences de lemmes ───────────────────────────────")
    by_period, glob = compute_freq_by_period(docs, y2p, args.supp_year)

    # ── 6. Tableau de contingence ──────────────────────────────────────
    print("\n── 6. Tableau de contingence ─────────────────────────────")
    df = build_contingency(by_period, labels, glob, args.min_freq, args.top_n)

    # Table brute (occurrences)
    df.to_csv(out_dir / "contingency_table.csv", encoding="utf-8-sig")
    print(f"  → contingency_table.csv")

    # Profils lignes : pour chaque lemme, distribution en fréquences relatives
    # sur les périodes (utile pour l'AFC et le calcul de spécificités)
    df_norm = df.div(df.sum(axis=1), axis=0).round(6)
    df_norm.to_csv(out_dir / "contingency_table_norm.csv", encoding="utf-8-sig")
    print(f"  → contingency_table_norm.csv")

    # Aperçu top 10 lemmes les plus fréquents
    print("\n  Aperçu (top 10 lemmes, occurrences brutes) :")
    top10 = df.sum(axis=1).sort_values(ascending=False).head(10).index
    print(df.loc[top10].to_string())

    # ── Bilan ──────────────────────────────────────────────────────────
    print(f"  ✓  Terminé → {out_dir.resolve()}")
    print(f"\n  Fichiers produits :")
    for fp in sorted(out_dir.glob("*")):
        size = fp.stat().st_size
        unit = "Ko" if size < 1_000_000 else "Mo"
        val  = size // 1024 if size < 1_000_000 else size // (1024 * 1024)
        print(f"    {fp.name:<40} {val:>5} {unit}")
    print("=" * 60)


if __name__ == "__main__":
    main()
