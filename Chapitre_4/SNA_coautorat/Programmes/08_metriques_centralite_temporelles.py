# Pour chaque année t (YEAR_MIN → YEAR_MAX), les deux graphes sont mis à jour
# de façon INCRÉMENTALE : on n'ajoute que les nouvelles publications de l'année
# t, sans jamais reconstruire le graphe depuis zéro.
#
#   Réseau auteur-auteur (G_simple, G_newman) :
#     Quand une publication avec k auteurs est ajoutée, on relie toutes les
#     paires d'auteurs entre eux (O(k²) opérations).
#     → Projection simple  : poids = nombre de publications partagées
#     → Projection Newman  : poids = Σ_p  1 / (k_p − 1)
#        où k_p est le nombre d'auteurs de la publication p.
#        Ce facteur pénalise les grandes collaborations (Newman, 2001).
#
#   Réseau publication-publication (G_pub) :
#     Quand une publication p est ajoutée avec des auteurs {a1, …, ak} :
#       Pour chaque auteur ai et pour chaque publication p' déjà signée par ai,
#       on incrémente le poids de l'arête (p, p') de 1 (nb d'auteurs partagés).
#     → O(k × nb_pubs_antérieures_de_ai) par publication, bien inférieur à une
#       reprojection complète depuis le graphe biparti.
#
# ─── INDICATEURS CALCULÉS (par année) ───────────────────────────────────────
#
# Indicateurs globaux :
#   n_noeuds, n_liens, densité, nb composantes, taille et % LCC,
#   diamètre LCC, clustering moyen, degré moyen, degré pondéré moyen.
#
# Indicateurs par nœud :
#   degree, closeness, betweenness (exacte, non pondérée), eigenvector.
#
#   PageRank et Katz ont été retirés de l'analyse :
#     - PageRank dépend fortement du paramètre d'amortissement (α = 0.85)
#       et s'avère redondant avec le degré pondéré dans nos données.
#     - Katz nécessite de calculer le spectre de la matrice d'adjacence à
#       chaque année (très coûteux) et converge mal sur des graphes déconnectés.
#     Ces deux métriques ne seront pas utilisées dans le rendu final.
#
#  Betweenness exacte (pas d'approximation par échantillonnage) :
#     Le calcul est topologique (non pondéré) : chaque arête compte pour 1,
#     indépendamment de son poids. On mesure ainsi la position structurelle
#     du nœud dans le graphe, sans que la force des liens n'influe sur les
#     plus courts chemins.
#     Le calcul est complet sur tous les nœuds. C'est intentionnel pour garantir
#     des résultats reproductibles et comparables d'une année à l'autre.
#     Sur de très grands réseaux (> 10 000 nœuds), cela peut être lent.
#



import os
import warnings
from collections import defaultdict
from pathlib import Path

import pandas as pd
import networkx as nx


EDGES_PATH = r"C:\Users\Enora\Documents\Université\Mémoire\CLE_USB\chapitre_4\SNA_coautorat\Noeuds_et_aretes\edges_author_pub.csv"
NODES_PATH = r"C:\Users\Enora\Documents\Université\Mémoire\CLE_USB\chapitre_4\SNA_coautorat\Noeuds_et_aretes\nodes_all.csv"

YEAR_MIN = 1975
YEAR_MAX = 2025

BASE_DIR   = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"
TEX_DIR    = OUTPUT_DIR / "tex"
TEMP_DIR   = OUTPUT_DIR / "temporal"

OUTPUT_PREFIX = str(TEMP_DIR / "result")

def _progress(step, total, label=""):
    """Affiche une barre de progression dans la console (mise à jour en place)."""
    bar_len = 30
    filled  = int(bar_len * step / total)
    bar     = "█" * filled + "░" * (bar_len - filled)
    print(f"\r  [{bar}] {step}/{total}  {label:<55}", end="", flush=True)
    if step == total:
        print()

def load_csv(path, required):
    """
    Charge un CSV en s'assurant que toutes les colonnes requises sont présentes.
    Les noms de colonnes sont normalisés (strip + minuscules) pour éviter les
    problèmes liés aux espaces ou à la casse.
    """
    df = pd.read_csv(path, dtype=str)
    df.columns = df.columns.str.strip().str.lower()
    for col in required:
        if col not in df.columns:
            raise ValueError(
                f"Colonne manquante : '{col}'\n"
                f"Colonnes trouvées : {list(df.columns)}"
            )
    return df


def load_network_data(nodes_path, edges_path):
    """
    Charge les fichiers CSV de nœuds et d'arêtes, puis :
      - convertit les poids et les années en numérique,
      - supprime les arêtes sans année (impossibles à situer dans le temps),
      - sépare les nœuds en deux sous-ensembles : auteurs et publications.

    Retourne :
      edges_df  — DataFrame des arêtes auteur→publication triées par année
      authors_df — DataFrame des nœuds de type "author"
      pubs_df    — DataFrame des nœuds de type "publication"
    """
    nodes_df = load_csv(nodes_path, required=["id", "type"])
    edges_df = load_csv(edges_path, required=["source", "target", "year"])

    # Le poids est optionnel dans le CSV ; on le fixe à 1 s'il est absent
    if "weight" in edges_df.columns:
        edges_df["weight"] = pd.to_numeric(edges_df["weight"], errors="coerce").fillna(1)
    else:
        edges_df["weight"] = 1

    # Conversion de l'année en entier, suppression des arêtes non datées
    edges_df["year"] = pd.to_numeric(edges_df["year"], errors="coerce")
    n_avant  = len(edges_df)
    edges_df = edges_df.dropna(subset=["year"])
    edges_df["year"] = edges_df["year"].astype(int)
    if n_avant != len(edges_df):
        print(f" {n_avant - len(edges_df):,} arêtes sans année ignorées")

    # Séparation auteurs / publications selon la colonne "type"
    authors_df = nodes_df[nodes_df["type"] == "author"].copy()
    pubs_df    = nodes_df[nodes_df["type"] == "publication"].copy()

    print(f"  Auteurs      : {len(authors_df):>6,}")
    print(f"  Publications : {len(pubs_df):>6,}")
    print(f"  Arêtes       : {len(edges_df):>6,}  "
          f"(années {edges_df['year'].min()}-{edges_df['year'].max()})")

    # Tri par année pour la cohérence de la mise à jour incrémentale
    edges_df = edges_df.sort_values("year").reset_index(drop=True)
    return edges_df, authors_df, pubs_df


def global_metrics_of(G, year, reseau):
    """
    Calcule les indicateurs structuraux globaux d'un graphe G pour une année
    et un type de réseau donnés.

    Paramètres :
      G       — graphe NetworkX (non orienté, pondéré)
      year    — année du snapshot cumulatif
      reseau  — étiquette identifiant le réseau (ex. "simple", "newman", "pub")

    Retourne un dict, ou None si le graphe est vide.

    Indicateurs calculés :
      n_noeuds         — nombre de nœuds dans le graphe
      n_liens          — nombre d'arêtes
      densite          — densité du graphe (entre 0 et 1)
      composantes      — nombre de composantes connexes
      taille_lcc       — taille de la plus grande composante connexe (LCC)
      pct_lcc          — % de nœuds dans la LCC
      diametre_lcc     — diamètre de la LCC (None si calcul impossible)
      clustering_moyen — coefficient de clustering moyen (pondéré)
      degre_moyen      — degré moyen (non pondéré)
    """
    if G is None or G.number_of_edges() == 0:
        return None

    n_cc  = nx.number_connected_components(G)
    lcc   = max(nx.connected_components(G), key=len)
    G_lcc = G.subgraph(lcc)

    # Le diamètre est calculé sur la LCC uniquement (le graphe complet peut
    # être déconnecté, auquel cas le diamètre n'est pas défini globalement)
    try:
        diam = nx.diameter(G_lcc)
    except Exception:
        diam = None

    return {
        "year":             year,
        "reseau":           reseau,
        "n_noeuds":         G.number_of_nodes(),
        "n_liens":          G.number_of_edges(),
        "densite":          nx.density(G),
        "composantes":      n_cc,
        "taille_lcc":       len(lcc),
        "pct_lcc":          len(lcc) / G.number_of_nodes() * 100,
        "diametre_lcc":     diam,
        "clustering_moyen": nx.average_clustering(G, weight="weight"),
        "degre_moyen":      sum(d for _, d in G.degree()) / G.number_of_nodes(),
    }


def node_metrics_of(G, year, reseau):
    """
    Calcule les centralités nœud par nœud sur le graphe G.

    Paramètres :
      G      — graphe NetworkX (non orienté, pondéré)
      year   — année du snapshot cumulatif
      reseau — étiquette du réseau (pour traçabilité dans les CSV de sortie)

    Retourne un DataFrame avec une ligne par nœud.

    Centralités calculées :
      degree      — degré non pondéré (nb de voisins directs)
      closeness   — proximité : inverse de la somme des distances à tous
                    les autres nœuds (NetworkX normalise sur la LCC)
      betweenness — intermédiarité exacte : fraction de plus courts chemins
                    passant par le nœud, calculée de façon topologique
                    (non pondérée — chaque arête compte pour 1).
      eigenvector — centralité vecteur propre : un nœud est central s'il
                    est connecté à d'autres nœuds centraux

    (PageRank et Katz exclus — voir en-tête du script pour la justification.)
    """
    if G is None or G.number_of_edges() == 0:
        return pd.DataFrame()

    nodes = list(G.nodes())
    n     = len(nodes)
    rows  = {"id": nodes, "year": year, "reseau": reseau}

    # ── Degré ────────────────────────────────────────────────────────────────
    deg  = dict(G.degree())
    rows["degree"] = [deg[v] for v in nodes]

    # ── Closeness ─────────────────────────────────────────────────────────────
    # Dans un graphe déconnecté, NetworkX calcule la closeness sur la composante
    # du nœud et ajuste par le rapport (taille_composante / (n-1)).
    cl = nx.closeness_centrality(G)
    rows["closeness"] = [cl[v] for v in nodes]

    # ── Betweenness (EXACTE, NON PONDÉRÉE) ───────────────────────────────────
    # Calcul topologique : chaque arête a une distance de 1, indépendamment
    # de son poids. On mesure la position structurelle du nœud dans le graphe.
    # Calcul exact sur l'ensemble des nœuds, sans échantillonnage.
    # Peut être lent sur de très grands réseaux (> 10 000 nœuds).
    btw = nx.betweenness_centrality(G, normalized=True)
    rows["betweenness"] = [btw[v] for v in nodes]

    # ── Eigenvector ───────────────────────────────────────────────────────────
    # Peut ne pas converger sur des graphes déconnectés ou très hétérogènes ;
    # dans ce cas on affecte 0.0 à tous les nœuds plutôt que de lever une erreur.
    try:
        ev = nx.eigenvector_centrality(G, max_iter=1000, weight="weight")
        rows["eigenvector"] = [ev[v] for v in nodes]
    except nx.PowerIterationFailedConvergence:
        rows["eigenvector"] = [0.0] * n

    return pd.DataFrame(rows)


def _add_publication_coautorship(G_simple, G_newman, authors):
    """
    Met à jour incrémentalement G_simple et G_newman lorsqu'une nouvelle
    publication (dont la liste d'auteurs est fournie) est intégrée au graphe.

    Les deux projections sont mises à jour simultanément pour économiser
    un parcours de la liste d'auteurs.

    Projection simple  : poids(a, b) += 1 pour chaque publication co-signée.
    Projection Newman  : poids(a, b) += 1 / (k − 1) où k = nombre d'auteurs
                         de la publication. Ce facteur réduit le crédit accordé
                         aux très grandes collaborations (Newman, 2001).

    Si une publication n'a qu'un seul auteur (k < 2), le nœud est quand même
    ajouté au graphe (nœud isolé), mais aucune arête n'est créée.

    Complexité : O(k²) avec k = nombre d'auteurs de la publication.
    """
    k = len(authors)

    # Ajout des nœuds même pour les publications mono-auteur
    for a in authors:
        if not G_simple.has_node(a):
            G_simple.add_node(a)
            G_newman.add_node(a)

    if k < 2:
        return

    # Contribution Newman de cette publication (identique pour toutes les paires)
    nw_w = 1.0 / (k - 1)

    # Parcours de toutes les paires d'auteurs non ordonnées
    for i in range(k):
        for j in range(i + 1, k):
            a, b = authors[i], authors[j]

            # Projection simple : incrémentation du poids si l'arête existe déjà
            if G_simple.has_edge(a, b):
                G_simple[a][b]["weight"] += 1
            else:
                G_simple.add_edge(a, b, weight=1)

            # Projection Newman : même logique avec le poids ajusté
            if G_newman.has_edge(a, b):
                G_newman[a][b]["weight"] += nw_w
            else:
                G_newman.add_edge(a, b, weight=nw_w)


def _add_publication_pub_pub(G_pub, author_to_pubs, pub_id, pub_authors):
    """
    Ajoute la publication pub_id au graphe publication-publication G_pub
    de façon incrémentale.

    Pour chaque auteur ai de pub_id :
      - Pour chaque publication p' déjà signée par ai :
          G_pub[pub_id][p']['weight'] += 1   (nb d'auteurs partagés)
      - Enregistre pub_id dans author_to_pubs[ai] pour les futures mises à jour.

    La pondération retenue est donc le nombre d'auteurs communs entre deux
    publications (projection simple). La pondération de Newman pour les
    publications nécessiterait de mettre à jour rétroactivement tous les
    poids existants à chaque nouvelle publication d'un auteur déjà présent,
    ce qui est coûteux et incompatible avec l'approche incrémentale.

    Complexité : O(k × max_pubs_par_auteur) par publication.
    """
    # Ajout du nœud en nœud isolé si ce n'est pas déjà fait
    if not G_pub.has_node(pub_id):
        G_pub.add_node(pub_id)

    for author in pub_authors:
        # Lien avec chaque publication antérieure signée par le même auteur
        for prev_pub in author_to_pubs[author]:
            if G_pub.has_edge(pub_id, prev_pub):
                G_pub[pub_id][prev_pub]["weight"] += 1
            else:
                G_pub.add_edge(pub_id, prev_pub, weight=1)

        # Enregistrement pour les futures publications de cet auteur
        author_to_pubs[author].append(pub_id)


def run_temporal_analysis(edges_df, authors_df):
    """
    Boucle temporelle cumulative sur la plage [YEAR_MIN, YEAR_MAX].

    À chaque année t :
      1. On identifie les nouvelles publications parues en t.
      2. On met à jour incrémentalement les trois graphes :
           G_simple  — co-autorship, projection simple
           G_newman  — co-autorship, projection Newman
           G_pub     — publication-publication
      3. On calcule les indicateurs globaux et par nœud pour chacun.

    La mise à jour incrémentale évite de reconstruire les graphes depuis
    zéro chaque année : seules les nouvelles publications sont traitées,
    ce qui réduit fortement le temps de calcul sur de longues séries.

    Retourne :
      df_global — DataFrame des indicateurs globaux (1 ligne par année × réseau)
      df_nodes  — DataFrame des métriques par nœud (1 ligne par nœud × année × réseau)
    """
    print(f"\n--- 2. BOUCLE TEMPORELLE CUMULATIVE ({YEAR_MIN} → {YEAR_MAX}) ---")
    print(f"  Betweenness : exacte, non pondérée (calcul topologique complet)")
    print(f"  Réseaux     : auteur-auteur (simple + Newman) + publication-publication\n")

    author_ids = set(authors_df["id"])

    # Pré-calcul : regrouper les auteurs par publication et par année
    # Structure : { année → { pub_id → [auteur_id, …] } }
    pub_authors_by_year = defaultdict(lambda: defaultdict(list))
    subset = edges_df[edges_df["source"].isin(author_ids)]
    for _, row in subset.iterrows():
        pub_authors_by_year[int(row["year"])][row["target"]].append(row["source"])

    all_years = list(range(YEAR_MIN, YEAR_MAX + 1))
    n_years   = len(all_years)

    all_global = []   # liste de dicts → 1 ligne par (année × réseau)
    all_nodes  = []   # liste de DataFrames → concaténées à la fin

    # ── État des graphes en mémoire (mis à jour à chaque année) ──────────────
    G_simple       = nx.Graph()          # co-autorship, pondération simple
    G_newman       = nx.Graph()          # co-autorship, pondération Newman
    G_pub          = nx.Graph()          # publication-publication
    author_to_pubs = defaultdict(list)   # auteur → [pub_id, …] (pour G_pub)

    for step, year in enumerate(all_years, 1):
        _progress(step, n_years, f"année {year}")

        new_pubs = pub_authors_by_year.get(year, {})

        # ── Mise à jour incrémentale des trois graphes ────────────────────────
        for pub_id, pub_authors in new_pubs.items():
            _add_publication_coautorship(G_simple, G_newman, pub_authors)
            _add_publication_pub_pub(G_pub, author_to_pubs, pub_id, pub_authors)

        # ── Indicateurs (si le graphe a au moins une arête) ───────────────────
        for G, label in [(G_simple, "simple"), (G_newman, "newman"), (G_pub, "pub")]:
            if G.number_of_edges() == 0:
                continue

            gm = global_metrics_of(G, year, label)
            if gm:
                all_global.append(gm)

            # On passe une copie du graphe pour éviter toute interférence entre
            # le calcul des métriques et la mise à jour incrémentale suivante.
            df_n = node_metrics_of(G.copy(), year, label)
            if not df_n.empty:
                all_nodes.append(df_n)

        # Affichage intermédiaire tous les 5 ans pour suivre la progression
        if year % 5 == 0 and all_global:
            last = next((g for g in reversed(all_global)
                         if g["year"] == year and g["reseau"] == "simple"), None)
            if last:
                print(f"\n  {year}  |  {last['n_noeuds']:>5,} auteurs  "
                      f"|  {last['n_liens']:>6,} liens  "
                      f"|  densité {last['densite']:.5f}  "
                      f"|  LCC {last['pct_lcc']:.1f}%")

    print()

    df_global = pd.DataFrame(all_global)
    df_nodes  = pd.concat(all_nodes, ignore_index=True) if all_nodes else pd.DataFrame()

    print(f"  {len(df_global)} lignes d'indicateurs globaux (années × réseaux)")
    print(f"  {len(df_nodes):,} lignes de métriques par nœud")

    return df_global, df_nodes


def export_results(df_global, df_nodes):
    """
    Exporte les résultats dans des fichiers CSV et LaTeX.

    Fichiers générés dans TEMP_DIR :
      result_temporal_global.csv          — indicateurs globaux (toutes années × réseaux)
      result_temporal_global_pivot.csv    — idem, pivotés (une ligne par année)
      result_temporal_nodes.csv           — métriques par nœud (toutes années × réseaux)
      result_temporal_nodes_<reseau>.csv  — idem, un fichier par réseau
    """

    prefix = OUTPUT_PREFIX

    glob_csv = f"{prefix}_temporal_global.csv"
    df_global.to_csv(glob_csv, index=False)
    print(f"  {Path(glob_csv).name}")

    df_pivot = df_global.pivot(index="year", columns="reseau")
    df_pivot.columns = [f"{reseau}_{ind}" for ind, reseau in df_pivot.columns]
    df_pivot = df_pivot.reset_index()
    pivot_csv = f"{prefix}_temporal_global_pivot.csv"
    df_pivot.to_csv(pivot_csv, index=False)
    print(f"  {Path(pivot_csv).name}  (format pivot — une ligne par année)")

    df_pivot.to_latex(
        os.path.join(TEX_DIR, "temporal_global_pivot.tex"),
        index=False, float_format="%.4f",
        caption="Évolution annuelle des indicateurs globaux (réseau cumulatif)",
        label="tab:temporal_global"
    )
    print(f"  tex/temporal_global_pivot.tex")

    # ── Métriques par nœud ────────────────────────────────────────────────────
    if not df_nodes.empty:
        nodes_csv = f"{prefix}_temporal_nodes.csv"
        df_nodes.to_csv(nodes_csv, index=False)
        print(f"  {Path(nodes_csv).name}  ({len(df_nodes):,} lignes — nœud × année × réseau)")

        # Un fichier par réseau pour faciliter les analyses ciblées
        for reseau in df_nodes["reseau"].unique():
            sub = df_nodes[df_nodes["reseau"] == reseau]
            if not sub.empty:
                sub_csv = f"{prefix}_temporal_nodes_{reseau}.csv"
                sub.to_csv(sub_csv, index=False)
                print(f"  {Path(sub_csv).name}")

def main():
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        TEMP_DIR.mkdir(parents=True, exist_ok=True)
        TEX_DIR.mkdir(parents=True, exist_ok=True)

        edges_df, authors_df, pubs_df = load_network_data(NODES_PATH, EDGES_PATH)

        df_global, df_nodes = run_temporal_analysis(edges_df, authors_df)

        export_results(df_global, df_nodes)

        print("  TERMINÉ — Fichiers générés dans :")
        print(f"  {TEMP_DIR}")
        for f in sorted(TEMP_DIR.iterdir()):
            if f.is_file():
                print(f"    {f.name}")
        print("=" * 62)

    except Exception as e:
        import traceback
        print(f"\nErreur : {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main()
