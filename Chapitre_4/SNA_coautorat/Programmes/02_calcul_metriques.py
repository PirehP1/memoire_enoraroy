import json
import os
import warnings

import numpy as np
import pandas as pd
import networkx as nx
from networkx.algorithms import bipartite

from pathlib import Path

# Racine = dossier du script → remonte d'un niveau vers SNA_coautorat
BASE_DIR   = Path(__file__).resolve().parent.parent

NODES_FILE = BASE_DIR / "Noeuds_et_aretes" / "nodes_all.csv"
EDGES_FILE = BASE_DIR / "Noeuds_et_aretes" / "edges_author_pub.csv"
OUTPUT_DIR = BASE_DIR / "output"
TEX_DIR    = OUTPUT_DIR / "tex"
# Seuil au-delà duquel le diamètre n'est pas calculé (trop coûteux)
MAX_NODES_DIAMETER = 100000 #ici précisément pas limité car c'est pour l'envoi


#permet de charger les csv et les données en construisant deux ensembles, un pour les publications
#et un pour les auteurs
def _load_csv(path, required):
    df = pd.read_csv(path, dtype=str)
    df.columns = df.columns.str.strip().str.lower()
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Colonnes manquantes dans {path} : {missing}")
    return df


def load_data(nodes_path, edges_path):
    print("\n─── CHARGEMENT ───")
    nodes_df = _load_csv(nodes_path, ["id", "type"])
    edges_df = _load_csv(edges_path, ["source", "target"])
    edges_df["weight"] = 1.0
    authors_df = nodes_df[nodes_df["type"] == "author"].copy()
    pubs_df    = nodes_df[nodes_df["type"] == "publication"].copy()
    print(f"  Auteurs      : {len(authors_df):,}")
    print(f"  Publications : {len(pubs_df):,}")
    print(f"  Arêtes       : {len(edges_df):,}")

    return nodes_df, edges_df, authors_df, pubs_df


def build_projections(nodes_df, edges_df, authors_df, pubs_df):
    """
    Construit le graphe biparti et projette sur AUTEURS et PUBLICATIONS.
    Retourne 4 graphes :
      G_as : projection auteurs, poids = nb publications communes (simple)
      G_an : projection auteurs, poids Newman = sum_p 1/(n_p - 1)
      G_ps : projection publications, poids = nb auteurs partagés (simple)
      G_pn : projection publications, poids Newman = sum_a 1/(k_a - 1)
    """
    A = set(authors_df["id"])
    P = set(pubs_df["id"])

    B = nx.Graph()
    B.add_nodes_from(A, bipartite=0)
    B.add_nodes_from(P, bipartite=1)

    valid = edges_df[edges_df["source"].isin(A) & edges_df["target"].isin(P)]
    for r in valid.itertuples():
        B.add_edge(r.source, r.target, weight=float(r.weight))

    print(f"  Biparti : {B.number_of_nodes():,} nœuds / {B.number_of_edges():,} arêtes")

    # Projections AUTEURS
    G_as = bipartite.weighted_projected_graph(B, A)
    G_an = bipartite.collaboration_weighted_projected_graph(B, A)

    # Projections PUBLICATIONS
    G_ps = bipartite.weighted_projected_graph(B, P)
    G_pn = bipartite.collaboration_weighted_projected_graph(B, P)

    print(f"  Auteurs simple  : {G_as.number_of_nodes():,} nœuds / {G_as.number_of_edges():,} liens")
    print(f"  Auteurs Newman  : {G_an.number_of_nodes():,} nœuds / {G_an.number_of_edges():,} liens")
    print(f"  Pubs simple     : {G_ps.number_of_nodes():,} nœuds / {G_ps.number_of_edges():,} liens")
    print(f"  Pubs Newman     : {G_pn.number_of_nodes():,} nœuds / {G_pn.number_of_edges():,} liens")

    return G_as, G_an, G_ps, G_pn


def compute_global_metrics(G, prefix, label, node_type="Nœuds"):
    """
    Calcule et exporte les indicateurs globaux d'un graphe projeté.
    Fichiers produits : _global_metrics.csv, .json, .tex
    """
    print(f"\n  Indicateurs globaux ({label})...")

    lcc      = max(nx.connected_components(G), key=len)
    G_lcc    = G.subgraph(lcc).copy()

    # Le diamètre exact est coûteux sur de grands graphes
    if len(lcc) <= MAX_NODES_DIAMETER:
        diameter = nx.diameter(G_lcc)
    else:
        diameter = "N/A (trop grand)"

    stats = {
        "Indicateur": [
            node_type, "Liens", "Densité",
            "Composantes connexes", "Taille LCC",
            "Diamètre (composante géante)", "Clustering moyen", "Degré moyen"
        ],
        "Valeur": [
            G.number_of_nodes(),
            G.number_of_edges(),
            nx.density(G),
            nx.number_connected_components(G),
            len(lcc),
            diameter,
            # [C3] FIX : clustering pondéré (weight="weight"), pas le clustering binaire
            nx.average_clustering(G, weight="weight"),
            sum(dict(G.degree()).values()) / max(G.number_of_nodes(), 1)
        ]
    }

    df = pd.DataFrame(stats)
    df.to_csv(f"{prefix}_global_metrics.csv", index=False)

    with open(f"{prefix}_global_metrics.json", "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    tex_out = TEX_DIR / f"{Path(prefix).name}_global_metrics.tex"
    df.to_latex(
        tex_out, index=False, float_format="%.4f",
        caption=f"Indicateurs globaux — {label}",
        label=f"tab:global_{Path(prefix).name}"
    )

    for ind, val in zip(stats["Indicateur"], stats["Valeur"]):
        print(f"    {ind:<38} : {val}")


def compute_node_metrics(G, col_prefix=""):
    """
    Calcule les métriques de centralité pour chaque nœud du graphe G.

    col_prefix : préfixe des colonnes (ex. "" pour simple, "nw" pour Newman).
    """
    p     = col_prefix + "_" if col_prefix else ""
    nodes = list(G.nodes())

    print(f"\n  [{col_prefix or 'simple'}] Calcul des métriques ({len(nodes):,} nœuds)...")

    # Degré
    print(f"    Degré...")
    degree   = dict(G.degree())
    degree_w = dict(G.degree(weight="weight"))

    # Betweenness
    print(f"    Betweenness...")
    btw = nx.betweenness_centrality(G, weight="weight", normalized=True)

    # Closeness
    print(f"    Closeness...")
    clo = nx.closeness_centrality(G)

    # PageRank
    print(f"    PageRank...")
    pr = nx.pagerank(G, alpha=0.85, weight="weight")

    # [C2] Katz — alpha dynamique basé sur le plus grand eigenvalue
    print(f"    Katz...")
    try:
        phi        = max(nx.adjacency_spectrum(G).real)
        katz_alpha = 0.85 / phi if phi > 0 else 0.005
        katz       = nx.katz_centrality(G, alpha=katz_alpha, max_iter=2000)
    except Exception:
        print(f"    Katz non convergée, remplie à 0")
        katz = {n: 0.0 for n in nodes}

    # Eigenvector
    print(f"    Eigenvector...")
    try:
        ev = nx.eigenvector_centrality(G, max_iter=1000, weight="weight")
    except nx.PowerIterationFailedConvergence:
        print(f"    Eigenvector non convergée, remplie à 0")
        ev = {n: 0.0 for n in nodes}

    # Clustering pondéré
    print(f"    Clustering...")
    clust = nx.clustering(G, weight="weight")

    return pd.DataFrame({
        "id":              nodes,
        f"{p}degree":      [degree[n]   for n in nodes],
        f"{p}degree_w":    [degree_w[n] for n in nodes],
        f"{p}betweenness": [btw[n]      for n in nodes],
        f"{p}closeness":   [clo[n]      for n in nodes],
        f"{p}pagerank":    [pr[n]       for n in nodes],
        f"{p}katz":        [katz[n]     for n in nodes],
        f"{p}eigenvector": [ev[n]       for n in nodes],
        f"{p}clustering":  [clust[n]    for n in nodes],
    })



def export_graph(G_simple, G_newman, df_simple, df_newman,
                 output_prefix, meta_drop_cols=None):
    """
    Export GraphML (Gephi-ready) pour les projections simple et Newman.
    Export des listes d'arêtes en CSV.
    Export d'un CSV fusionné (colonnes simple + Newman) pour les nœuds.
    """
    if meta_drop_cols is None:
        meta_drop_cols = []

    for G, df, suffix in [
        (G_simple, df_simple, "simple"),
        (G_newman, df_newman, "newman"),
    ]:
        # Injecte quelques attributs utiles dans le graphe avant export
        for col in ["degree", "pagerank", "betweenness", "label", "year"]:
            col_in_df = (col if col in df.columns
                         else f"nw_{col}" if f"nw_{col}" in df.columns
                         else None)
            if col_in_df and col_in_df in df.columns:
                nx.set_node_attributes(
                    G, df.set_index("id")[col_in_df].to_dict(), col
                )

        # [C5] GraphML
        gml_path = f"{output_prefix}_{suffix}.graphml"
        nx.write_graphml(G, gml_path)
        print(f"  {Path(gml_path).name}  (Gephi-ready)")

        # [C6] Arêtes CSV
        edges_list = [
            {"source": u, "target": v, "weight": d.get("weight", 1)}
            for u, v, d in G.edges(data=True)
        ]
        edge_csv = f"{output_prefix}_edges_{suffix}.csv"
        pd.DataFrame(edges_list).to_csv(edge_csv, index=False)
        print(f"  {Path(edge_csv).name}")

    # [C7] Fusion simple + Newman dans un seul CSV nœuds
    drop = [c for c in meta_drop_cols if c in df_newman.columns]
    df_merged = df_simple.merge(
        df_newman.drop(columns=drop, errors="ignore"),
        on="id", how="outer"
    )
    node_csv = f"{output_prefix}_nodes_all.csv"
    df_merged.to_csv(node_csv, index=False)
    print(f"  {Path(node_csv).name}  (colonnes simple + Newman fusionnées)")


def run():
    OUTPUT_DIR.mkdir(exist_ok=True, parents=True)
    TEX_DIR.mkdir(exist_ok=True, parents=True)

    nodes, edges, authors, pubs = load_data(NODES_FILE, EDGES_FILE)

    # ── 2. Projections ───────────────────────────────────────────────────────
    G_as, G_an, G_ps, G_pn = build_projections(nodes, edges, authors, pubs)

    # ── 3. Indicateurs globaux ───────────────────────────────────────────────
    compute_global_metrics(G_as, f"{OUTPUT_DIR}/result_auteur_simple",
                           "Auteurs – projection simple",   node_type="Auteurs (nœuds)")
    compute_global_metrics(G_an, f"{OUTPUT_DIR}/result_auteur_newman",
                           "Auteurs – projection Newman",   node_type="Auteurs (nœuds)")
    compute_global_metrics(G_ps, f"{OUTPUT_DIR}/result_pub_simple",
                           "Publications – projection simple", node_type="Publications (nœuds)")
    compute_global_metrics(G_pn, f"{OUTPUT_DIR}/result_pub_newman",
                           "Publications – projection Newman", node_type="Publications (nœuds)")

    # ── 4. Métriques par nœud ────────────────────────────────────────────────
    print("\n─── MÉTRIQUES PAR NŒUD — AUTEURS ───")

    df_as = compute_node_metrics(G_as, col_prefix="")
    # [C8] Enrichissement métadonnées auteurs (label, genre…)
    author_meta = [c for c in ["id", "label", "genre"] if c in authors.columns]
    df_as = df_as.merge(authors[author_meta], on="id", how="left")
    df_as.to_csv(f"{OUTPUT_DIR}/auteur_simple_nodes.csv", index=False)

    df_an = compute_node_metrics(G_an, col_prefix="nw")
    df_an = df_an.merge(authors[author_meta], on="id", how="left")
    df_an.to_csv(f"{OUTPUT_DIR}/auteur_newman_nodes.csv", index=False)

    print("\n─── MÉTRIQUES PAR NŒUD — PUBLICATIONS ───")

    df_ps = compute_node_metrics(G_ps, col_prefix="")
    pub_meta = [c for c in ["id", "label", "year", "language",
                             "topic_id", "label_thema", "nb_auteurs"]
                if c in pubs.columns]
    df_ps = df_ps.merge(pubs[pub_meta], on="id", how="left")
    df_ps.to_csv(f"{OUTPUT_DIR}/pub_simple_nodes.csv", index=False)

    df_pn = compute_node_metrics(G_pn, col_prefix="nw")
    df_pn = df_pn.merge(pubs[pub_meta], on="id", how="left")
    df_pn.to_csv(f"{OUTPUT_DIR}/pub_newman_nodes.csv", index=False)

    # ── 5. Export GraphML + arêtes + nœuds fusionnés ─────────────────────────
    print("\n─── EXPORT GRAPHML & CSV ───")

    export_graph(
        G_as, G_an, df_as, df_an,
        output_prefix=f"{OUTPUT_DIR}/result_coauthorship",
        meta_drop_cols=["label", "genre"]
    )

    export_graph(
        G_ps, G_pn, df_ps, df_pn,
        output_prefix=f"{OUTPUT_DIR}/result_pub",
        meta_drop_cols=["label", "year", "language",
                        "topic_id", "label_thema", "nb_auteurs"]
    )
    print("  TERMINÉ")

if __name__ == "__main__":
    run()
