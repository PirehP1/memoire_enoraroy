import numpy as np
import pandas as pd
import networkx as nx
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from pathlib import Path

BASE       = Path(__file__).resolve().parent.parent

EDGES_PATH = BASE / "Noeuds_et_aretes" / "edges_author_pub.csv"
NODES_PATH = BASE / "Noeuds_et_aretes" / "nodes_all.csv"
OUTPUT_DIR = BASE / "output"
OUTPUT     = OUTPUT_DIR / "boxplots_coauteurs"

def load_data():
    edges_df = pd.read_csv(EDGES_PATH).rename(columns=lambda x: x.strip().lower())
    nodes_df = pd.read_csv(NODES_PATH).rename(columns=lambda x: x.strip().lower())
    
    for col in ["source", "target"]: edges_df[col] = edges_df[col].astype(str).str.strip()
    nodes_df["id"] = nodes_df["id"].astype(str).str.strip()
    
    print(f"   → {len(nodes_df)} nœuds  |  {len(edges_df)} arêtes")
    return edges_df, nodes_df

def build_graph(edges_df, nodes_df):
    print("Construction du graphe biparti...")
    G = nx.from_pandas_edgelist(edges_df, source="source", target="target")
    
    node_types = dict(zip(nodes_df["id"], nodes_df["type"].str.lower()))
    nx.set_node_attributes(G, node_types, name="node_type")
    
    print(f"   → {G.number_of_nodes()} nœuds, {G.number_of_edges()} arêtes")
    return G

def get_distributions(G, nodes_df):
    print("Calcul des co-auteurs par composante...")
    
    authors = set(nodes_df.loc[nodes_df["type"].str.lower() == "author", "id"])
    print(f"   → {len(authors)} auteurs")

    components = sorted(nx.connected_components(G), key=len, reverse=True)
    print(f"   → {len(components)} composantes connexes")

    coauthor_counts = {}
    for a in authors:
        if a in G:
            nbrs = {nbr for pub in G.neighbors(a) for nbr in G.neighbors(pub) if nbr != a and nbr in authors}
            coauthor_counts[a] = max(len(nbrs), 1)

    counts_main = [coauthor_counts[a] for a in components[0] if a in coauthor_counts]
    counts_other = [coauthor_counts[a] for cc in components[1:] for a in cc if a in coauthor_counts]

    return counts_main, counts_other, len(components)

def plot_boxplots(counts_main, counts_other, n_components):
    print("Génération des boxplots...")
    fig, axes = plt.subplots(2, 1, figsize=(11, 7))
    fig.suptitle("Distribution du nombre de co-auteurs par auteur\nselon la composante connexe (réseau biparti)", fontsize=13, fontweight="bold")

    datasets = [
        (counts_main, "#2E86AB", "Composante connexe principale"),
        (counts_other, "#E07A5F", f"Autres composantes connexes ({n_components - 1})"),
    ]
    
    xmax = max(counts_main + counts_other) if (counts_main + counts_other) else 1

    for ax, (data, color, title) in zip(axes, datasets):
        if data:
            bp = ax.boxplot(data, vert=False, patch_artist=True, widths=0.45,
                            medianprops=dict(color="white", linewidth=2.5),
                            whiskerprops=dict(linewidth=1.5), capprops=dict(linewidth=1.5),
                            flierprops=dict(marker="o", markerfacecolor=color, markersize=4, alpha=0.4, linestyle="none"))
            bp["boxes"][0].set_facecolor(color)
            bp["boxes"][0].set_alpha(0.82)
            
            stats_label = f"n = {len(data)}    médiane = {np.median(data):.1f}    Q1 = {np.percentile(data, 25):.1f}    Q3 = {np.percentile(data, 75):.1f}    max = {max(data)}"
            ax.legend(handles=[plt.Rectangle((0, 0), 1, 1, fc=color, alpha=0.82)], labels=[stats_label], loc="lower right", fontsize=9, framealpha=0.9, edgecolor=color)
        else:
            ax.text(0.5, 0.5, "Aucune donnée", ha="center", va="center", transform=ax.transAxes, fontsize=11, color="gray")

        ax.set_xscale("log")
        ax.set_xlim(1, xmax)
        ax.set_title(title, fontsize=11, fontweight="bold", loc="left", pad=6)
        ax.set_xlabel("Nombre de co-auteurs", fontsize=10)
        ax.set_yticks([])
        ax.xaxis.set_minor_locator(ticker.LogLocator(base=10.0, subs="auto"))
        ax.grid(axis="x", linestyle="--", alpha=0.5)
        ax.spines[["top", "right", "left"]].set_visible(False)

    plt.tight_layout()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)  # ← corrigé : crée le dossier si besoin
    plt.savefig(f"{OUTPUT}.png", dpi=300, bbox_inches="tight")
    plt.savefig(f"{OUTPUT}.svg", bbox_inches="tight")
    print(f"   → {OUTPUT}.png  &  {OUTPUT}.svg\nTerminé.")
    plt.show()

if __name__ == "__main__":
    edges_df, nodes_df = load_data()
    G = build_graph(edges_df, nodes_df)
    counts_main, counts_other, n_comp = get_distributions(G, nodes_df)
    plot_boxplots(counts_main, counts_other, n_comp)
