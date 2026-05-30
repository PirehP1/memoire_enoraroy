from pathlib import Path
import numpy as np
import pandas as pd
import networkx as nx
from scipy.stats import spearmanr
import matplotlib
matplotlib.use("Agg") 
import matplotlib.pyplot as plt
import seaborn as sns

BASE_DIR = Path(__file__).resolve().parent.parent

NODES_CSV = BASE_DIR / "Noeuds_et_aretes" / "nodes_all.csv"
EDGES_CSV = BASE_DIR / "Noeuds_et_aretes" / "edges_author_pub.csv"

AUTEUR_SIMPLE_CSV = BASE_DIR / "output" / "auteur_simple_nodes.csv"
AUTEUR_NEWMAN_CSV = BASE_DIR / "output" / "auteur_newman_nodes.csv"
PUB_SIMPLE_CSV    = BASE_DIR / "output" / "pub_simple_nodes.csv"
PUB_NEWMAN_CSV    = BASE_DIR / "output" / "pub_newman_nodes.csv"

OUTPUT_DIR = BASE_DIR / "output"
TEX_DIR    = OUTPUT_DIR / "tex"
IMG_DIR    = OUTPUT_DIR / "img"

METRICS_SIMPLE = [
    "degree",
    "betweenness",
    "eigenvector",
    "pagerank",
    "clustering"
]

METRICS_NEWMAN = [
    "nw_degree",
    "nw_betweenness",
    "nw_eigenvector",
    "nw_pagerank",
    "nw_clustering"
]

METRIC_LABELS = {
    "degree":          "Degré",
    "betweenness":     "Betweenness",
    "eigenvector":     "Eigenvector",
    "pagerank":        "PageRank",
    "clustering":      "Clustering",
    "nw_degree":       "Degré (Newman)",
    "nw_betweenness":  "Betweenness (Newman)",
    "nw_eigenvector":  "Eigenvector (Newman)",
    "nw_pagerank":     "PageRank (Newman)",
    "nw_clustering":   "Clustering (Newman)",
}

def _load(path, required=None):
    """Charge un fichier CSV en forçant le type string pour éviter les pertes de données 
    sur les identifiants textuels, et passe les en-têtes en minuscules."""
    df = pd.read_csv(path, dtype=str, low_memory=False)
    df.columns = df.columns.str.strip().str.lower()
    if required:
        for col in required:
            if col not in df.columns:
                raise ValueError(
                    f"Colonne manquante : '{col}' dans {path}\n"
                    f"Colonnes trouvées : {list(df.columns)}"
                )
    return df

def _to_float(df, cols):
    """Convertit les colonnes de métriques cibles en réels (float) pour les calculs statistiques."""
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def build_lcc(nodes_path, links_path):
    """Reconstruit le réseau bipartite (Auteurs-Publications) pour identifier la 
    plus grande composante connexe (LCC). Permet d'éliminer les artefacts ou les 
    structures isolées avant de corréler les indicateurs."""
    print("\n--- 1. RECONSTRUCTION LCC ---")
    nodes_df = _load(nodes_path, required=["id", "type"])
    edges_df = _load(links_path, required=["source", "target"])

    # Séparation des nœuds par type
    all_aut = set(nodes_df[nodes_df["type"] == "author"]["id"])
    all_pub = set(nodes_df[nodes_df["type"] == "publication"]["id"])

    # Initialisation du graphe NetworkX
    B = nx.Graph()
    B.add_nodes_from(all_aut, bipartite=0)
    B.add_nodes_from(all_pub, bipartite=1)

    # Filtrage et injection des liens valides (qui relient bien un auteur à une publication)
    valid = edges_df[
        edges_df["source"].isin(all_aut) &
        edges_df["target"].isin(all_pub)
    ]
    for _, r in valid.iterrows():
        B.add_edge(r["source"], r["target"])

    # Extraction de la plus grande composante connexe (LCC)
    lcc     = max(nx.connected_components(B), key=len)
    lcc_aut = lcc & all_aut
    lcc_pub = lcc & all_pub

    print(f"BDD : {len(all_aut)} auteurs | {len(all_pub)} publications | {nx.number_connected_components(B)} composantes")
    print(f"LCC : {len(lcc_aut)} auteurs | {len(lcc_pub)} publications ({len(lcc)/B.number_of_nodes()*100:.1f}% des noeuds)")
    return lcc_aut, lcc_pub

def load_metrics_data(filepath, lcc_filter, metrics_list, is_publication=False):
    """Charge un fichier de métriques, applique le filtre de la LCC, et isole 
    les colonnes numériques d'indicateurs configurées."""
    p = Path(filepath)
    if not p.exists():
        print(f"Fichier introuvable : {p}")
        return pd.DataFrame(), []

    df = _load(str(p))
    print(f"Source : {p.name} ({len(df)} lignes brutes)")

    # Alignement sur la LCC
    n_avant = len(df)
    df = df[df["id"].isin(lcc_filter)].copy()
    print(f"Filtre LCC : {n_avant} -> {len(df)} noeuds retenus")

    # Si traitement de publications : gestion des doublons temporels (garde la dernière version connue)
    if is_publication and "year" in df.columns:
        df["year"] = pd.to_numeric(df["year"], errors="coerce")
        last_year  = int(df["year"].max())
        df         = df.sort_values("year").groupby("id", as_index=False).last()
        print(f"Snapshot annee {last_year} : {len(df)} publications uniques retenues")

    # Nettoyage des types numériques
    df = _to_float(df, metrics_list)
    avail = [m for m in metrics_list if m in df.columns]
    print(f"Indicateurs disponibles : {avail}")
    
    return df[["id"] + avail].copy(), avail


def compute_spearman(df, avail):
    """Calcule les coefficients de corrélation de Spearman (rho) ainsi que les 
    valeurs de p associées pour chaque paire de variables disponibles."""
    n   = len(avail)
    rho = np.zeros((n, n))
    pv  = np.ones((n, n))

    # Suppression des lignes entièrement vides sur les métriques sélectionnées
    sub = df[avail].dropna(how="all")

    for i, ci in enumerate(avail):
        for j, cj in enumerate(avail):
            if i == j:
                rho[i, j] = 1.0
                pv[i, j]  = 0.0
                continue
            
            # Alignement (pairwise deletion) des données manquantes pour la paire courante
            mask = sub[ci].notna() & sub[cj].notna()
            xi   = sub.loc[mask, ci].values
            xj   = sub.loc[mask, cj].values
            
            # Un minimum de 5 observations est requis pour que le test de Spearman ait du sens
            if len(xi) < 5:
                rho[i, j] = np.nan
                pv[i, j]  = np.nan
            else:
                r, p      = spearmanr(xi, xj)
                rho[i, j] = r
                pv[i, j]  = p

    # Mise en forme sous forme de DataFrames indexés avec les labels lisibles
    labels  = [METRIC_LABELS.get(m, m) for m in avail]
    df_rho  = pd.DataFrame(rho, index=labels, columns=labels)
    df_pval = pd.DataFrame(pv,  index=labels, columns=labels)
    return df_rho, df_pval


def plot_heatmap(df_rho, df_pval, title, img_path, tex_path, n_obs):
    """Génère la matrice visuelle sous forme de heatmap (triangle inférieur uniquement) 
    et produit le tableau LaTeX correspondant. Affiche le rho et la valeur de p brute."""
    n      = len(df_rho)
    labels = list(df_rho.columns)

    # Création du masque pour masquer le triangle supérieur (évite la redondance visuelle)
    mask_upper = np.triu(np.ones((n, n), dtype=bool), k=1)

    # Génération de la matrice d'annotations textuelles : "rho (p=valeur)"
    annot = np.full((n, n), "", dtype=object)
    for i in range(n):
        for j in range(n):
            if i == j:
                annot[i, j] = "1.000"
            elif not mask_upper[i, j]:
                r_val = df_rho.iloc[i, j]
                p_val = df_pval.iloc[i, j]
                # Formatage de p : notation scientifique si très proche de 0, sinon 3 décimales
                p_str = f"{p_val:.3e}" if p_val < 0.001 else f"{p_val:.3f}"
                annot[i, j] = f"{r_val:.3f}\n(p={p_str})"

    fig, ax = plt.subplots(figsize=(max(9, n * 1.4), max(8, n * 1.3)))

    sns.heatmap(
        df_rho,
        ax=ax,
        mask=mask_upper,
        annot=annot,
        fmt="",
        cmap="RdBu_r", # Palette divergente classique (Bleu = positif, Rouge = négatif)
        vmin=-1, vmax=1, center=0,
        square=True,
        linewidths=0.5,
        linecolor="#dddddd",
        annot_kws={"size": 8, "weight": "normal"},
        cbar_kws={"label": "Rho de Spearman", "shrink": 0.8},
    )

    for i in range(n):
        ax.add_patch(
            plt.Rectangle((i, i), 1, 1, fill=True, color="#e8e8e8", lw=0, zorder=2)
        )
        ax.text(i + 0.5, i + 0.5, "1.000", ha="center", va="center", fontsize=8, color="#999999", style="italic")

    # Titre et mise en forme des axes
    ax.set_title(
        f"{title}\n"
        f"Correlations de Spearman — n = {n_obs} (LCC)\n"
        "Affichage : coefficient rho (valeur de p brute)",
        fontsize=11, pad=14
    )
    ax.set_xticklabels(labels, rotation=40, ha="right", fontsize=9)
    ax.set_yticklabels(labels, rotation=0, fontsize=9)

    plt.tight_layout()
    fig.savefig(str(img_path), dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Export image : {Path(img_path).name}")

    # --- EXPORT LATEX ---
    df_tex = pd.DataFrame(annot, index=labels, columns=labels, dtype=str)
    for i in range(n):
        for j in range(i + 1, n):
            df_tex.iloc[i, j] = ""

    caption = (
        f"{title}. "
        "Correlations de Spearman (triangle inferieur). "
        f"Chaque cellule presente le coefficient rho suivi de la valeur de p brute entre parentheses. "
        f"n = {n_obs} noeuds (composante connexe principale, snapshot 2025)."
    )
    with open(str(tex_path), "w", encoding="utf-8") as f:
        f.write(
            df_tex.to_latex(
                caption=caption,
                label="tab:corr_" + Path(tex_path).stem,
                escape=False,
            )
        )
    print(f"Export LaTeX : {Path(tex_path).name}")


def main():
    try:
        print("HEATMAPS CORRELATIONS SPEARMAN — LCC")
        
        TEX_DIR.mkdir(parents=True, exist_ok=True)
        IMG_DIR.mkdir(parents=True, exist_ok=True)

        lcc_aut, lcc_pub = build_lcc(NODES_CSV, EDGES_CSV)

        # 1. AUTEURS - PROJECTION SIMPLE
        print("\n--- 2a. AUTEURS - PROJECTION SIMPLE ---")
        df_aut_s, avail_aut_s = load_metrics_data(AUTEUR_SIMPLE_CSV, lcc_aut, METRICS_SIMPLE)
        if not df_aut_s.empty and len(avail_aut_s) >= 2:
            print(f"Calcul des correlations pour {len(df_aut_s)} auteurs...")
            rho, pv = compute_spearman(df_aut_s, avail_aut_s)
            plot_heatmap(
                rho, pv,
                title="Correlations — Auteurs (projection simple)",
                img_path=IMG_DIR / "heatmap_corr_auteurs_simple.png",
                tex_path=TEX_DIR / "heatmap_corr_auteurs_simple.tex",
                n_obs=len(df_aut_s),
            )

        # 2. AUTEURS - PROJECTION NEWMAN
        print("\n--- 2b. AUTEURS - PROJECTION NEWMAN ---")
        df_aut_n, avail_aut_n = load_metrics_data(AUTEUR_NEWMAN_CSV, lcc_aut, METRICS_NEWMAN)
        if not df_aut_n.empty and len(avail_aut_n) >= 2:
            print(f"Calcul des correlations pour {len(df_aut_n)} auteurs...")
            rho, pv = compute_spearman(df_aut_n, avail_aut_n)
            plot_heatmap(
                rho, pv,
                title="Correlations — Auteurs (projection Newman)",
                img_path=IMG_DIR / "heatmap_corr_auteurs_newman.png",
                tex_path=TEX_DIR / "heatmap_corr_auteurs_newman.tex",
                n_obs=len(df_aut_n),
            )

        # 3. PUBLICATIONS - PROJECTION SIMPLE
        print("\n--- 2c. PUBLICATIONS - PROJECTION SIMPLE ---")
        df_pub_s, avail_pub_s = load_metrics_data(PUB_SIMPLE_CSV, lcc_pub, METRICS_SIMPLE, is_publication=True)
        if not df_pub_s.empty and len(avail_pub_s) >= 2:
            print(f"Calcul des correlations pour {len(df_pub_s)} publications...")
            rho, pv = compute_spearman(df_pub_s, avail_pub_s)
            plot_heatmap(
                rho, pv,
                title="Correlations — Publications (projection simple)",
                img_path=IMG_DIR / "heatmap_corr_publications_simple.png",
                tex_path=TEX_DIR / "heatmap_corr_publications_simple.tex",
                n_obs=len(df_pub_s),
            )

        # 4. PUBLICATIONS - PROJECTION NEWMAN
        print("\n--- 2d. PUBLICATIONS - PROJECTION NEWMAN ---")
        df_pub_n, avail_pub_n = load_metrics_data(PUB_NEWMAN_CSV, lcc_pub, METRICS_NEWMAN, is_publication=True)
        if not df_pub_n.empty and len(avail_pub_n) >= 2:
            print(f"Calcul des correlations pour {len(df_pub_n)} publications...")
            rho, pv = compute_spearman(df_pub_n, avail_pub_n)
            plot_heatmap(
                rho, pv,
                title="Correlations — Publications (projection Newman)",
                img_path=IMG_DIR / "heatmap_corr_publications_newman.png",
                tex_path=TEX_DIR / "heatmap_corr_publications_newman.tex",
                n_obs=len(df_pub_n),
            )

        print("\nTraitement termine avec succes.")

    except Exception as e:
        import traceback
        print(f"\nErreur lors de l'execution : {e}")
        traceback.print_exc()

if __name__ == "__main__":
    main()
