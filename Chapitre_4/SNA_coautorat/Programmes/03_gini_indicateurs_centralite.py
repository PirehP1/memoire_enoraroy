import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

BASE       = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE / "output"
aut = pd.read_csv(OUTPUT_DIR / "auteur_simple_nodes.csv", dtype=str, low_memory=False)
pub = pd.read_csv(OUTPUT_DIR / "pub_simple_nodes.csv",    dtype=str, low_memory=False)

# Snapshot dernière année par publication (même logique que script 7)
pub["year"] = pd.to_numeric(pub["year"], errors="coerce")
pub = pub.sort_values("year").groupby("id", as_index=False).last()

METRICS = ["degree", "betweenness", "pagerank", "katz", "eigenvector", "clustering"]
OUT = OUTPUT_DIR / "img"
OUT.mkdir(parents=True, exist_ok=True)

# ── Fonctions ─────────────────────────────────────────────────────────────────
def gini(v):
    v = np.sort(v[v > 0])
    n = len(v)
    if n == 0:
        return np.nan
    return (2 * np.sum(np.arange(1, n + 1) * v) / (n * v.sum())) - (n + 1) / n

def lorenz(v):
    v = np.sort(v[v > 0])
    cs = np.cumsum(v)
    return np.linspace(0, 1, len(v)), cs / cs[-1]

def plot_lorenz(values, metric, label, color, outpath):
    v = pd.to_numeric(values, errors="coerce").dropna().values
    v = v[v > 0]
    if len(v) < 5:
        print(f"  {metric} : pas assez de données")
        return
    x, y = lorenz(v)
    g = gini(v)
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.plot([0, 1], [0, 1], "k--", lw=1, alpha=0.4, label="Égalité parfaite")
    ax.plot(x, y, lw=2, color=color, label=f"G = {g:.3f}")
    ax.fill_between(x, x, y, alpha=0.1, color=color)
    ax.set_title(f"{metric}\n{label}  (N={len(v):,})", fontsize=11)
    ax.set_xlabel("Part cumulée des nœuds")
    ax.set_ylabel("Part cumulée de l'indicateur")
    ax.legend(fontsize=9)
    ax.grid(alpha=0.25, linestyle=":")
    ax.spines[["top", "right"]].set_visible(False)
    plt.tight_layout()
    fig.savefig(str(outpath), dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  -> {outpath.name}  (Gini = {g:.3f})")

# ── Auteurs ───────────────────────────────────────────────────────────────────
print("\n=== AUTEURS ===")
for m in METRICS:
    if m in aut.columns:
        plot_lorenz(aut[m], m, "Auteurs (LCC)", "#4C9BE8",
                    OUT / f"lorenz_auteurs_{m}.png")

# ── Publications ──────────────────────────────────────────────────────────────
print("\n=== PUBLICATIONS ===")
for m in METRICS:
    if m in pub.columns:
        plot_lorenz(pub[m], m, "Publications (LCC)", "#E87B4C",
                    OUT / f"lorenz_publications_{m}.png")

print("\nTerminé.")
