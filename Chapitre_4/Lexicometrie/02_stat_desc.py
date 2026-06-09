"""
Statistiques descriptives du corpus brut (avant prétraitement).

Ce script analyse corpus_complet.json produit par A_build_corpus.py,
AVANT toute application de stopwords, filtres POS ou seuils fréquentiels.
Son rôle est de valider et de caractériser la matière première du corpus
avant que celui-ci ne soit nettoyé en corpus_propre.json.

Sorties (dossier --output, défaut : output/stats_corpus/) :
    stats_generales.txt
    group_sizes_par_annee.csv
    top30_lemmes.csv
    01_group_sizes_features.pdf
    02_group_sizes_types.pdf
    03_group_sizes_hapax.pdf
    04_evolution_temporelle.pdf
    05_distribution_longueur.pdf


Usage :
    python stats_corpus_complet.py corpus_complet.json
    python stats_corpus_complet.py corpus_complet.json --output output/stats
"""

import argparse
import pathlib
import sys

import pandas as pd
import matplotlib
matplotlib.use("Agg")   # Backend sans affichage (script batch ou serveur)
import matplotlib.pyplot as plt

from lexploreur.corpus      import *
from lexploreur.description import *
from lexploreur.utils       import *  

from sklearn.feature_extraction.text import CountVectorizer

def save_fig(path: pathlib.Path) -> None:
    """Sauvegarde la figure courante en PDF et ferme proprement."""
    plt.savefig(str(path), format="pdf", bbox_inches="tight")
    plt.close()
    print(f"  → {path.name}")


def main():
    parser = argparse.ArgumentParser(
        description="Calcule les statistiques descriptives d'un corpus JSON brut."
    )
    parser.add_argument("corpus",
        help="Chemin vers corpus_complet.json (produit par A_build_corpus.py).")
    parser.add_argument("--output", default="output/stats_corpus",
        help="Dossier de sortie (défaut : output/stats_corpus/).")
    args = parser.parse_args()

    corpus_path = pathlib.Path(args.corpus)
    out_dir     = pathlib.Path(args.output)

    if not corpus_path.exists():
        print(f"\n[ERREUR] Corpus JSON introuvable : {corpus_path}")
        print("Lancez d'abord : python A_build_corpus.py")
        sys.exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)

    print("STATISTIQUES DU CORPUS (avant prétraitement)")

    # ── 1. Vue lexicale par année ─────────────────────────────────────
    # Un groupe = une année. Sert au DTM, aux group_sizes et au top lemmes.
    # Aucun filtre : toutes les POS, aucun stopword → corpus brut.
    print("\n── 1. Vue lexicale par année (toutes POS, sans filtre) ───")
    df_lv_year = lexical_view(
        str(corpus_path),
        feature_to_extract="lemma",
        stopwords=[],
        lowercase=True,
        exclude_pos=[],
        exclude_tokens=[],
        group_by="year",
    )
    print(f"  {len(df_lv_year)} années dans le corpus")

    # ── 2. Vue lexicale par document ──────────────────────────────────
    # Sans group_by : une ligne = un document. Sert aux statistiques de
    # longueur (nb tokens par document) et à la distribution des longueurs.
    print("\n── 2. Vue lexicale par document ──────────────────────────")
    df_lv_doc = lexical_view(
        str(corpus_path),
        feature_to_extract="lemma",
        stopwords=[],
        lowercase=True,
        exclude_pos=[],
        exclude_tokens=[],
    )
    print(f"  {len(df_lv_doc)} documents")

    # ── 3. Construction du DTM ────────────────────────────────────────
    # CountVectorizer reçoit des listes de lemmes déjà tokenisées.
    # tokenizer=nothing et preprocessor=nothing désactivent les traitements
    # internes de CountVectorizer pour travailler directement sur les listes.
    print("\n── 3. Construction de la matrice termes-documents (DTM) ──")
    vec = CountVectorizer(
        tokenizer=nothing,
        preprocessor=nothing,
        token_pattern=None,
    )
    X   = vec.fit_transform(df_lv_year["lemma"])
    dtm = pd.DataFrame(
        X.toarray(),
        columns=vec.get_feature_names_out(),
        index=df_lv_year["year"],
    )
    print(f"  DTM : {dtm.shape[0]} années × {dtm.shape[1]:,} lemmes uniques")

    # ── 4. group_sizes ────────────────────────────────────────────────
    # group_sizes() calcule pour chaque groupe (année) :
    #   features = nb total d'occurrences
    #   types    = nb de lemmes uniques
    #   hapax    = nb de lemmes n'apparaissant qu'une seule fois
    print("\n── 4. group_sizes() par année ────────────────────────────")
    gs = group_sizes(dtm)
    print(gs.to_string())
    gs_path = out_dir / "group_sizes_par_annee.csv"
    gs.to_csv(gs_path, encoding="utf-8-sig")
    print(f"\n  → {gs_path.name}")

    # ── 5. Statistiques générales ─────────────────────────────────────
    print("\n── 5. Statistiques générales ─────────────────────────────")

    nb_docs   = len(df_lv_doc)
    nb_tokens = int(gs["features"].sum())

    # Lemmes uniques : colonnes avec au moins une occurrence dans tout le corpus
    totals    = dtm.sum(axis=0)
    nb_lemmes = int((totals > 0).sum())

    # Hapax : lemmes n'apparaissant qu'une seule fois dans l'ensemble du corpus
    nb_hapax  = int((totals == 1).sum())

    annees_min = int(df_lv_year["year"].min())
    annees_max = int(df_lv_year["year"].max())

    # Longueur des documents en nombre de lemmes
    doc_lengths = df_lv_doc["lemma"].apply(len)
    len_moy     = doc_lengths.mean()
    len_med     = doc_lengths.median()
    len_min     = int(doc_lengths.min())
    len_max     = int(doc_lengths.max())

    stats_lines = [
        "STATISTIQUES GÉNÉRALES DU CORPUS (avant prétraitement)",
        f"  Nb documents            : {nb_docs:,}",
        f"  Plage temporelle        : {annees_min} – {annees_max}",
        "",
        "  --- LEMMES ---",
        f"  Nb total d'occurrences  : {nb_tokens:,}",
        f"  Nb de lemmes uniques    : {nb_lemmes:,}",
        f"  Nb d'hapax              : {nb_hapax:,}  "
        f"({nb_hapax / nb_lemmes * 100:.1f}% des lemmes)",
        "",
        "  --- LONGUEUR DES DOCUMENTS (nb lemmes) ---",
        f"  Moyenne                 : {len_moy:.0f}",
        f"  Médiane                 : {len_med:.0f}",
        f"  Min                     : {len_min:,}",
        f"  Max                     : {len_max:,}",
    ]

    stats_str = "\n".join(stats_lines)
    print("\n" + stats_str)

    stats_path = out_dir / "stats_generales.txt"
    stats_path.write_text(stats_str, encoding="utf-8")
    print(f"\n  → {stats_path.name}")

    # ── 6. Top 30 lemmes ──────────────────────────────────────────────
    print("\n── 6. Top 30 lemmes les plus fréquents ───────────────────")

    # rename_axis + reset_index(name=...) est plus robuste que rename(columns={0: ...})
    # qui dépend implicitement de l'absence de nom sur la Series.
    top30 = (
        totals
        .sort_values(ascending=False)
        .head(30)
        .rename_axis("lemme")
        .reset_index(name="freq")
    )
    top30.to_csv(out_dir / "top30_lemmes.csv", index=False, encoding="utf-8-sig")
    print("\n  Top 10 lemmes :")
    print(top30.head(10).to_string(index=False))
    print("  → top30_lemmes.csv")

    # ── 7. Visualisations ─────────────────────────────────────────────
    print("\n── 7. Visualisations ─────────────────────────────────────")

    # 7a. group_sizes pour chaque dimension (features / types / hapax)
    for col, num in [("features", "01"), ("types", "02"), ("hapax", "03")]:
        plot_group_sizes(gs, col)
        save_fig(out_dir / f"{num}_group_sizes_{col}.pdf")

    # 7b. Évolution temporelle : les trois courbes sur un même graphique.
    # Permet de visualiser simultanément la richesse du corpus (types),
    # son volume (features) et sa rareté lexicale (hapax) au fil des années.
    fig, ax = plt.subplots(figsize=(12, 5))
    years   = gs.index.astype(str)
    ax.plot(years, gs["features"], "o-", label="Occurrences (features)",
            color="#2c7bb6", lw=2)
    ax.plot(years, gs["types"],   "s-", label="Lemmes uniques (types)",
            color="#1a9641", lw=2)
    ax.plot(years, gs["hapax"],   "^-", label="Hapax",
            color="#d7191c", lw=2)
    ax.set_xlabel("Année")
    ax.set_ylabel("Nombre")
    ax.set_title("Évolution temporelle du corpus\n"
                 "(occurrences, lemmes uniques, hapax par année)", fontsize=12)
    ax.legend(fontsize=9)
    ax.tick_params(axis="x", rotation=70, labelsize=8)
    ax.grid(True, alpha=0.35)
    plt.tight_layout()
    save_fig(out_dir / "04_evolution_temporelle.pdf")

    # 7c. Distribution des longueurs de documents.
    # Les lignes verticales (moyenne, médiane) aident à repérer d'éventuels
    # documents aberrants à exclure avant constitution du corpus propre.
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.hist(doc_lengths, bins=40, color="#2c7bb6", edgecolor="white", alpha=0.85)
    ax.axvline(len_moy, color="#d7191c", ls="--", lw=1.8,
               label=f"Moyenne : {len_moy:.0f}")
    ax.axvline(len_med, color="#ff7f00", ls=":",  lw=1.8,
               label=f"Médiane : {len_med:.0f}")
    ax.set_xlabel("Nb de lemmes par document")
    ax.set_ylabel("Nb de documents")
    ax.set_title("Distribution de la longueur des documents (lemmes bruts)",
                 fontsize=12)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.35, axis="y")
    plt.tight_layout()
    save_fig(out_dir / "05_distribution_longueur.pdf")

    print(f"\n  ✓ Terminé → {out_dir.resolve()}")


if __name__ == "__main__":
    main()
