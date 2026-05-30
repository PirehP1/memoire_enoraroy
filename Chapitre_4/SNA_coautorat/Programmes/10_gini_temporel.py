"""
gini_temporel.py
──────────────────────────────────────────────────────────────────────────────
Évolution du coefficient de Gini au fil du temps (réseau cumulatif),
séparément pour les AUTEURS et les PUBLICATIONS.

À chaque année t :
  1. Reconstruction du réseau bipartite cumulatif (arêtes ≤ t)
  2. Identification de la LCC (composante connexe principale)
  3. Filtrage des nœuds du fichier temporel à ceux présents dans la LCC
  4. Calcul du Gini pour : degree, closeness, betweenness, eigenvector

Sorties :
  output/img/gini_evolution_auteurs.png
  output/img/gini_evolution_publications.png
  output/gini_temporel_auteurs.csv
  output/gini_temporel_publications.csv

Fichiers d'entrée attendus (produits par 03_analyse_temporelle.py) :
  output/temporal/result_temporal_nodes_simple.csv  — auteurs (projection simple)
  output/temporal/result_temporal_nodes_pub.csv     — publications
──────────────────────────────────────────────────────────────────────────────
"""

import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import networkx as nx
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE_DIR   = Path(__file__).resolve().parent.parent
EDGES_PATH = BASE_DIR / "Noeuds_et_aretes" / "edges_author_pub.csv"

OUTPUT_DIR    = BASE_DIR / "output"
TEMP_DIR      = OUTPUT_DIR / "temporal"
TEMP_AUT_PATH = TEMP_DIR / "result_temporal_nodes_simple.csv"
TEMP_PUB_PATH = TEMP_DIR / "result_temporal_nodes_pub.csv"

METRICS = ["degree", "closeness", "betweenness", "eigenvector"]

METRIC_LABELS = {
    "degree":      "Degré",
    "closeness":   "Closeness",
    "betweenness": "Betweenness",
    "eigenvector": "Eigenvector",
}

COLORS = {
    "degree":      "#4C9BE8",
    "closeness":   "#E87B4C",
    "betweenness": "#2CA02C",
    "eigenvector": "#9467BD",
}


# ══════════════════════════════════════════════════════════════════════════════
# UTILITAIRES
# ══════════════════════════════════════════════════════════════════════════════

def gini(arr):
    """Coefficient de Gini. Ignore les NaN. Retourne NaN si vide ou somme nulle."""
    v = np.sort(arr[~np.isnan(arr)].astype(float))
    v = v[v >= 0]
    n = len(v)
    if n == 0 or v.sum() == 0:
        return np.nan
    return (2 * np.sum(np.arange(1, n + 1) * v) / (n * v.sum())) - (n + 1) / n


def load_edges(edges_path):
    """Charge le fichier d'arêtes, retourne un DataFrame avec colonnes normalisées."""
    df = pd.read_csv(edges_path, dtype=str, low_memory=False)
    df.columns = df.columns.str.strip().str.lower()
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df = df.dropna(subset=["year"])
    df["year"] = df["year"].astype(int)
    return df[["source", "target", "year"]].dropna()


def lcc_nodes_at(df_edges, year):
    """
    Construit le graphe bipartite cumulatif jusqu'à `year` et retourne
    l'ensemble des nœuds dans la LCC.
    """
    sub = df_edges[df_edges["year"] <= year]
    if sub.empty:
        return set()
    G = nx.Graph()
    G.add_edges_from(zip(sub["source"], sub["target"]))
    if G.number_of_nodes() == 0:
        return set()
    lcc = max(nx.connected_components(G), key=len)
    return lcc


def load_temporal(path):
    """
    Charge un fichier temporel produit par 03_analyse_temporelle.py.
    Normalise les colonnes et convertit les métriques en numérique.

    Note : les fichiers sont déjà filtrés par réseau (un fichier par réseau),
    donc aucun filtre sur la colonne "reseau" n'est nécessaire ici.
    Cette colonne remplace l'ancienne colonne "projection" de l'architecture
    précédente — elle est conservée dans le fichier mais ignorée à la lecture.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Fichier introuvable : {p}")
    df = pd.read_csv(str(p), dtype=str, low_memory=False)
    df.columns = df.columns.str.strip().str.lower()
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df = df.dropna(subset=["year"])
    df["year"] = df["year"].astype(int)
    for m in METRICS:
        if m in df.columns:
            df[m] = pd.to_numeric(df[m], errors="coerce")
    return df


# ══════════════════════════════════════════════════════════════════════════════
# CALCUL DU GINI PAR ANNÉE
# ══════════════════════════════════════════════════════════════════════════════

def compute_gini_series(df_temporal, df_edges, entity_label):
    """
    Pour chaque année dans df_temporal :
      - Reconstruit la LCC à cet instant
      - Filtre les lignes de df_temporal correspondant à l'année ET dans la LCC
      - Calcule le Gini pour chaque métrique disponible
    Retourne un DataFrame (year × métrique).
    """
    years = sorted(df_temporal["year"].unique())
    rows  = []

    for yr in years:
        lcc = lcc_nodes_at(df_edges, yr)
        if len(lcc) < 3:
            continue

        # Filtrage : lignes de cette année, nœud dans la LCC
        snap = df_temporal[
            (df_temporal["year"] == yr) &
            (df_temporal["id"].isin(lcc))
        ]
        if len(snap) < 3:
            continue

        row = {"year": yr, "n_lcc": len(snap)}
        for m in METRICS:
            if m in snap.columns:
                row[f"gini_{m}"] = gini(snap[m].values)
            else:
                row[f"gini_{m}"] = np.nan

        rows.append(row)
        avail = [m for m in METRICS if f"gini_{m}" in row]
        vals  = "  ".join(
            f"{m}={row[f'gini_{m}']:.3f}" for m in avail
            if not np.isnan(row.get(f"gini_{m}", np.nan))
        )
        print(f"  {entity_label} | {yr} | LCC={row['n_lcc']:>5} | {vals}")

    return pd.DataFrame(rows)


# ══════════════════════════════════════════════════════════════════════════════
# FIGURE
# ══════════════════════════════════════════════════════════════════════════════

def plot_gini(df_gini, entity_label, out_path):
    """
    Planche unique : une courbe par métrique, évolution du Gini sur le temps.
    Axe secondaire (barres grises) : taille de la LCC.
    """
    avail = [m for m in METRICS if f"gini_{m}" in df_gini.columns]
    if not avail or df_gini.empty:
        print(f"  ⚠  Pas de données Gini pour {entity_label}")
        return

    fig, ax1 = plt.subplots(figsize=(13, 5))

    # Barres de la taille de la LCC (arrière-plan)
    if "n_lcc" in df_gini.columns:
        ax2 = ax1.twinx()
        ax2.bar(df_gini["year"], df_gini["n_lcc"],
                width=0.7, color="#CCCCCC", alpha=0.30, zorder=1,
                label="Taille LCC")
        ax2.set_ylabel("Taille LCC", fontsize=9, color="#999999")
        ax2.tick_params(axis="y", labelcolor="#999999", labelsize=8)
        ax2.set_ylim(0, df_gini["n_lcc"].max() * 4)
        ax2.yaxis.set_major_formatter(
            plt.FuncFormatter(lambda x, _: f"{int(x):,}")
        )

    # Courbes Gini
    for m in avail:
        col  = f"gini_{m}"
        vals = df_gini[col]
        mask = vals.notna()
        if mask.sum() < 2:
            continue
        ax1.plot(
            df_gini.loc[mask, "year"], vals[mask],
            "o-", lw=2, ms=4,
            color=COLORS.get(m, "#333333"),
            label=METRIC_LABELS.get(m, m),
            alpha=0.90, zorder=3,
        )

    ax1.set_xlabel("Année (réseau cumulatif)", fontsize=10)
    ax1.set_ylabel("Coefficient de Gini", fontsize=10)
    ax1.set_ylim(-0.02, 1.05)
    ax1.set_title(
        f"Évolution du coefficient de Gini — {entity_label}\n"
        "(réseau bipartite cumulatif, LCC uniquement, un point = une année)",
        fontsize=11, pad=10
    )
    ax1.legend(loc="upper left", fontsize=9, title="Indicateur")
    ax1.grid(True, alpha=0.25, zorder=0)
    ax1.axhline(0, color="black", lw=0.5, ls=":")

    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(out_path), dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  → {out_path.name}")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    img_dir = OUTPUT_DIR / "img"

    print("=" * 60)
    print("  ÉVOLUTION DU GINI — RÉSEAU CUMULATIF (LCC)")
    print("=" * 60)

    # Chargement des arêtes (commun aux deux analyses)
    print("\n  Chargement des arêtes...")
    df_edges = load_edges(EDGES_PATH)
    years_all = sorted(df_edges["year"].unique())
    print(f"  {len(df_edges):,} arêtes | {years_all[0]}–{years_all[-1]}")

    # ── AUTEURS ───────────────────────────────────────────────────────────────
    print(f"\n━━  AUTEURS  ({TEMP_AUT_PATH.name})  ━━")
    df_aut = load_temporal(TEMP_AUT_PATH)
    print(f"  {df_aut['id'].nunique():,} auteurs uniques | "
          f"{df_aut['year'].nunique()} années")

    df_gini_aut = compute_gini_series(df_aut, df_edges, "Auteurs")
    df_gini_aut.to_csv(OUTPUT_DIR / "gini_temporel_auteurs.csv",
                       index=False, float_format="%.6f")
    plot_gini(df_gini_aut, "Auteurs",
              img_dir / "gini_evolution_auteurs.png")

    # ── PUBLICATIONS ──────────────────────────────────────────────────────────
    print(f"\n━━  PUBLICATIONS  ({TEMP_PUB_PATH.name})  ━━")
    df_pub = load_temporal(TEMP_PUB_PATH)
    print(f"  {df_pub['id'].nunique():,} publications uniques | "
          f"{df_pub['year'].nunique()} années")

    df_gini_pub = compute_gini_series(df_pub, df_edges, "Publications")
    df_gini_pub.to_csv(OUTPUT_DIR / "gini_temporel_publications.csv",
                       index=False, float_format="%.6f")
    plot_gini(df_gini_pub, "Publications",
              img_dir / "gini_evolution_publications.png")

    print("\n" + "=" * 60)
    print("  TERMINÉ")
    for f in sorted(img_dir.glob("gini_evolution_*.png")):
        print(f"    {f}")
    print("=" * 60)


if __name__ == "__main__":
    main()
