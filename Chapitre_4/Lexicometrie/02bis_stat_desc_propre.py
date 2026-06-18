"""
Statistiques descriptives du corpus propre et comparaison avec le corpus complet.

Ce script analyse corpus_propre.json 
et le compare avec les statistiques du corpus complet produites par
02_stat_desc.py 

Sorties (dossier --output, défaut : output/stats_corpus_propre/) :
    stats_generales_propre.txt
    stats_tokens_par_doc.txt / .csv
    comparaison_complet_propre.txt / .csv
    group_sizes_par_annee.csv
    top30_lemmes_propre.csv
    01_group_sizes_features.pdf
    02_group_sizes_types.pdf
    03_group_sizes_hapax.pdf
    04_evolution_temporelle.pdf
    05_distribution_longueur.pdf
    06_comparaison_features.pdf
    07_comparaison_types.pdf
    08_comparaison_hapax.pdf

Usage :
    python stats_corpus_propre.py corpus_propre.json
    python stats_corpus_propre.py corpus_propre.json \\
        --stats-complet output/stats_corpus \\
        --output output/stats_corpus_propre
"""

import argparse
import pathlib
import sys

import pandas as pd
import matplotlib
matplotlib.use("Agg")
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


def build_dtm(df_lv: pd.DataFrame, col: str = "lemma") -> tuple:
    """
    Construit une DTM (matrice termes-documents) à partir d'une vue lexicale
    lexploreur. La colonne `col` contient des listes de tokens déjà tokenisées ;
    tokenizer=nothing et preprocessor=nothing désactivent les traitements
    internes de CountVectorizer pour travailler directement sur ces listes.

    Retourne (dtm, vectorizer).
    """
    vec = CountVectorizer(
        tokenizer=nothing,
        preprocessor=nothing,
        token_pattern=None,
    )
    #transformation en sac de mots
    X   = vec.fit_transform(df_lv[col])
    #conversion en dataframe
    dtm = pd.DataFrame(
        X.toarray(),
        columns=vec.get_feature_names_out(),
        index=df_lv["year"], #index pour l'année, agrégation temporelle
    )
    return dtm, vec


def align_index(series_a: pd.Series, series_b: pd.Series) -> tuple:
    """Aligne deux séries sur l'union de leurs index, avec fill_value=0."""
    #permet de comparer corpus propre et corpus bruité
    idx = series_a.index.union(series_b.index)
    return series_a.reindex(idx, fill_value=0), series_b.reindex(idx, fill_value=0)


def read_stat(path: pathlib.Path, label: str) -> str:
    """
    Extrait la valeur d'un indicateur depuis un fichier stats_generales.txt.
    Retourne "N/A" si le fichier est absent ou si le label n'est pas trouvé.

    ⚠ Les labels doivent correspondre exactement au format produit par
    stats_corpus_complet.py. Si ce fichier est modifié, mettre à jour
    les appels ci-dessous en conséquence.
    """
    if not path.exists():
        return "N/A"
    for line in path.read_text(encoding="utf-8").splitlines():
        if label in line:
            return line.split(":")[-1].strip()
    return "N/A"


def pct_reduction(before_str: str, after_val: float) -> str:
    """
    Calcule la réduction en % entre une valeur "avant" (extraite comme chaîne
    depuis stats_generales.txt) et une valeur "après" (numérique).
    Retourne "N/A" si la conversion de before_str échoue.
    """
    try:
        # Les valeurs peuvent contenir des séparateurs de milliers (",") ou
        # des annotations supplémentaires "(X.X% des lemmes)".
        before_val = float(before_str.replace(",", "").split()[0])
        return f"−{(1 - after_val / before_val) * 100:.1f}%"
    except Exception:
        return "N/A"


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Statistiques du corpus propre et comparaison avec le corpus complet."
        )
    )
    parser.add_argument("corpus",
        help="Chemin vers corpus_propre.json.")
    parser.add_argument("--stats-complet", default="output/stats_corpus",
        dest="stats_complet",
        help="Dossier de sortie de stats_corpus_complet.py "
             "(défaut : output/stats_corpus/).")
    parser.add_argument("--output", default="output/stats_corpus_propre",
        help="Dossier de sortie (défaut : output/stats_corpus_propre/).")
    args = parser.parse_args()

    corpus_path      = pathlib.Path(args.corpus)
    stats_complet_dir = pathlib.Path(args.stats_complet)
    out_dir           = pathlib.Path(args.output)

    if not corpus_path.exists():
        print(f"\n[ERREUR] corpus_propre.json introuvable : {corpus_path}")
        print("Lancez d'abord : python C_build_corpus_propre.py")
        sys.exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)

    # Vérification de la disponibilité des stats du corpus complet
    gs_complet_path  = stats_complet_dir / "group_sizes_par_annee.csv"
    stats_txt_path   = stats_complet_dir / "stats_generales.txt"
    has_complet      = gs_complet_path.exists()
    if not has_complet:
        print(f"\n[AVERTISSEMENT] group_sizes du corpus complet introuvable :")
        print(f"  {gs_complet_path}")
        print("  Comparaison ignorée. Lancez stats_corpus_complet.py pour l'activer.\n")

    # ── 1. Vue lexicale par année ─────────────────────────────────────
    # Aucun filtre : statistiques sur les lemmes tels qu'ils sont dans le
    # corpus propre, avant tout filtrage POS ou stopwords supplémentaire.
    print("\n── 1. Vue lexicale par année ─────────────────────────────")
    df_lv_year = lexical_view(
        str(corpus_path),
        feature_to_extract="lemma",
        stopwords=[],
        lowercase=True,
        exclude_pos=[],
        exclude_tokens=[],
        group_by="year",
    )
    print(f"  {len(df_lv_year)} années dans le corpus propre")

    # ── 2. Vue lexicale par document ──────────────────────────────────
    # Sans group_by : une ligne = un document. Sert aux statistiques de
    # longueur (distribution du nb de lemmes par document).
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

    # doc_lengths calculée une seule fois ici — réutilisée dans toutes
    # les sections suivantes (stats descriptives, export, graphiques).
    doc_lengths = df_lv_doc["lemma"].apply(len)
    len_moy     = doc_lengths.mean()
    len_med     = doc_lengths.median()
    len_min     = int(doc_lengths.min())
    len_max     = int(doc_lengths.max())

    # ── 3. Statistiques de longueur par document ──────────────────────
    print("\n── 3. Statistiques de longueur par document ──────────────")

    stats_tokens = {
        "min":      len_min,
        "max":      len_max,
        "moyenne":  round(len_moy, 1),
        "mediane":  round(len_med, 1),
        "q25":      round(float(doc_lengths.quantile(0.25)), 1),
        "q75":      round(float(doc_lengths.quantile(0.75)), 1),
    }
    tokens_lines = [
        "STATISTIQUES NB DE TOKENS PAR DOCUMENT",
        "=" * 45,
        f"  Min      : {stats_tokens['min']:,}",
        f"  Max      : {stats_tokens['max']:,}",
        f"  Moyenne  : {stats_tokens['moyenne']:,}",
        f"  Médiane  : {stats_tokens['mediane']:,}",
        f"  Q25      : {stats_tokens['q25']:,}",
        f"  Q75      : {stats_tokens['q75']:,}",
    ]
    tokens_str = "\n".join(tokens_lines)
    print("\n" + tokens_str)
    (out_dir / "stats_tokens_par_doc.txt").write_text(tokens_str, encoding="utf-8")
    pd.DataFrame([stats_tokens]).to_csv(
        out_dir / "stats_tokens_par_doc.csv", index=False, encoding="utf-8-sig"
    )
    print("\n  → stats_tokens_par_doc.txt\n  → stats_tokens_par_doc.csv")

    # ── 4. DTM + group_sizes ──────────────────────────────────────────
    print("\n── 4. DTM + group_sizes ──────────────────────────────────")
    dtm_propre, _ = build_dtm(df_lv_year, "lemma")
    print(f"  DTM : {dtm_propre.shape[0]} années × {dtm_propre.shape[1]:,} lemmes")

    gs_propre = group_sizes(dtm_propre)
    gs_propre.to_csv(out_dir / "group_sizes_par_annee.csv", encoding="utf-8-sig")
    print("  → group_sizes_par_annee.csv")

    # ── 5. Statistiques générales — corpus propre ─────────────────────
    print("\n── 5. Statistiques générales ─────────────────────────────")

    nb_docs   = len(df_lv_doc)
    nb_tokens = int(gs_propre["features"].sum())
    totals    = dtm_propre.sum(axis=0)
    nb_types  = int((totals > 0).sum())
    nb_hapax  = int((totals == 1).sum())

    annees_min = int(df_lv_year["year"].min())
    annees_max = int(df_lv_year["year"].max())

    stats_lines = [
        "STATISTIQUES GÉNÉRALES DU CORPUS PROPRE",
        f"  Nb documents            : {nb_docs:,}",
        f"  Plage temporelle        : {annees_min} – {annees_max}",
        "",
        "  --- LEMMES ---",
        f"  Nb total d'occurrences  : {nb_tokens:,}",
        f"  Nb de lemmes uniques    : {nb_types:,}",
        f"  Nb d'hapax              : {nb_hapax:,}  "
        f"({nb_hapax / max(nb_types, 1) * 100:.1f}% des lemmes)",
        "",
        "  --- LONGUEUR DES DOCUMENTS (nb lemmes) ---",
        f"  Moyenne                 : {len_moy:.0f}",
        f"  Médiane                 : {len_med:.0f}",
        f"  Min                     : {len_min:,}",
        f"  Max                     : {len_max:,}",
    ]
    stats_str = "\n".join(stats_lines)
    print("\n" + stats_str)
    (out_dir / "stats_generales_propre.txt").write_text(stats_str, encoding="utf-8")
    print("\n  → stats_generales_propre.txt")

    # ── 6. Tableau comparatif complet / propre ────────────────────────
    # Les valeurs "avant" sont lues depuis stats_generales.txt du corpus
    # complet. Les labels ci-dessous doivent correspondre exactement au
    # format produit par stats_corpus_complet.py.
    print("\n── 6. Tableau comparatif complet / propre ────────────────")

    c_docs    = read_stat(stats_txt_path, "Nb documents")
    c_tokens  = read_stat(stats_txt_path, "Nb total d'occurrences")
    c_types   = read_stat(stats_txt_path, "Nb de lemmes uniques")
    c_hapax   = read_stat(stats_txt_path, "Nb d'hapax")       # label mis à jour
    c_len_moy = read_stat(stats_txt_path, "Moyenne")
    c_len_med = read_stat(stats_txt_path, "Médiane")

    rows_cmp = [
        ("Nb documents",        c_docs,    f"{nb_docs:,}",   pct_reduction(c_docs, nb_docs)),
        ("Nb occurrences",      c_tokens,  f"{nb_tokens:,}", pct_reduction(c_tokens, nb_tokens)),
        ("Nb lemmes uniques",   c_types,   f"{nb_types:,}",  pct_reduction(c_types, nb_types)),
        ("Nb hapax",            c_hapax,   f"{nb_hapax:,}",  pct_reduction(c_hapax, nb_hapax)),
        ("Longueur moy. (lem)", c_len_moy, f"{len_moy:.0f}", pct_reduction(c_len_moy, len_moy)),
        ("Longueur méd. (lem)", c_len_med, f"{len_med:.0f}", pct_reduction(c_len_med, len_med)),
    ]

    col_w  = [25, 16, 16, 12]
    sep    = "  " + "-" * (sum(col_w) + 9)
    header = (f"  {'Indicateur':<{col_w[0]}}"
              f"{'Corpus complet':>{col_w[1]}}"
              f"{'Corpus propre':>{col_w[2]}}"
              f"{'Réduction':>{col_w[3]}}")
    cmp_lines = [
        "COMPARAISON CORPUS COMPLET / CORPUS PROPRE",
        "=" * 65,
        header, sep,
    ]
    for label, val_c, val_p, pct in rows_cmp:
        cmp_lines.append(
            f"  {label:<{col_w[0]}}"
            f"{val_c:>{col_w[1]}}"
            f"{val_p:>{col_w[2]}}"
            f"{pct:>{col_w[3]}}"
        )
    cmp_lines.append(sep)
    cmp_str = "\n".join(cmp_lines)
    print("\n" + cmp_str)
    (out_dir / "comparaison_complet_propre.txt").write_text(cmp_str, encoding="utf-8")
    pd.DataFrame(rows_cmp, columns=[
        "indicateur", "corpus_complet", "corpus_propre", "reduction"
    ]).to_csv(
        out_dir / "comparaison_complet_propre.csv", index=False, encoding="utf-8-sig"
    )
    print("\n  → comparaison_complet_propre.txt\n  → comparaison_complet_propre.csv")

    # ── 7. Top 30 lemmes ──────────────────────────────────────────────
    print("\n── 7. Top 30 lemmes ──────────────────────────────────────")
    top30 = (
        totals
        .sort_values(ascending=False)
        .head(30)
        .rename_axis("lemme")
        .reset_index(name="freq")
    )
    top30.to_csv(out_dir / "top30_lemmes_propre.csv", index=False, encoding="utf-8-sig")
    print("  Top 10 lemmes :")
    print(top30.head(10).to_string(index=False))
    print("  → top30_lemmes_propre.csv")

    # ── 8. Visualisations — corpus propre seul ────────────────────────
    print("\n── 8. Visualisations corpus propre ───────────────────────")

    for col, num in [("features", "01"), ("types", "02"), ("hapax", "03")]:
        plot_group_sizes(gs_propre, col)
        save_fig(out_dir / f"{num}_group_sizes_{col}.pdf")

    # Évolution temporelle : les trois courbes sur un même graphique
    fig, ax = plt.subplots(figsize=(12, 5))
    years = gs_propre.index.astype(str)
    ax.plot(years, gs_propre["features"], "o-", label="Occurrences",
            color="#2c7bb6", lw=2)
    ax.plot(years, gs_propre["types"],   "s-", label="Lemmes uniques",
            color="#1a9641", lw=2)
    ax.plot(years, gs_propre["hapax"],   "^-", label="Hapax",
            color="#d7191c", lw=2)
    ax.set_xlabel("Année")
    ax.set_ylabel("Nombre")
    ax.set_title("Corpus propre — évolution temporelle\n"
                 "(occurrences, lemmes uniques, hapax par année)", fontsize=12)
    ax.legend(fontsize=9)
    ax.tick_params(axis="x", rotation=70, labelsize=8)
    ax.grid(True, alpha=0.35)
    plt.tight_layout()
    save_fig(out_dir / "04_evolution_temporelle.pdf")

    # Distribution des longueurs de documents
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.hist(doc_lengths, bins=40, color="#2c7bb6", edgecolor="white", alpha=0.85)
    ax.axvline(len_moy, color="#d7191c", ls="--", lw=1.8,
               label=f"Moyenne : {len_moy:.0f}")
    ax.axvline(len_med, color="#ff7f00", ls=":",  lw=1.8,
               label=f"Médiane : {len_med:.0f}")
    ax.set_xlabel("Nb de lemmes par document")
    ax.set_ylabel("Nb de documents")
    ax.set_title("Corpus propre — distribution des longueurs de documents",
                 fontsize=12)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.35, axis="y")
    plt.tight_layout()
    save_fig(out_dir / "05_distribution_longueur.pdf")

    # ── 9. Visualisations comparatives ────────────────────────────────
    # Chaque graphique superpose deux courbes (corpus complet vs propre)
    # avec un remplissage pour visualiser l'impact du prétraitement.
    if has_complet:
        print("\n── 9. Visualisations comparatives ────────────────────────")
        gs_complet = pd.read_csv(gs_complet_path, index_col=0, encoding="utf-8-sig")
        gs_complet.index   = gs_complet.index.astype(int)
        gs_propre_int      = gs_propre.copy()
        gs_propre_int.index = gs_propre_int.index.astype(int)

        for metric, num, color_c, color_p in [
            ("features", "06", "#2c7bb6", "#74add1"),
            ("types",    "07", "#1a9641", "#78c679"),
            ("hapax",    "08", "#d7191c", "#f4a582"),
        ]:
            if metric not in gs_complet.columns or metric not in gs_propre_int.columns:
                print(f"  [AVERTISSEMENT] colonne '{metric}' absente, graphique ignoré.")
                continue

            s_c, s_p   = align_index(gs_complet[metric], gs_propre_int[metric])
            years_all   = s_c.index.astype(str)

            fig, ax = plt.subplots(figsize=(13, 5))
            ax.plot(years_all, s_c.values, "o-",
                    label="Corpus complet", color=color_c, lw=2, ms=5)
            ax.plot(years_all, s_p.values, "s--",
                    label="Corpus propre",  color=color_p, lw=2, ms=5)
            # Zone grisée : différence = impact du prétraitement (filtres, exclusions)
            ax.fill_between(years_all, s_c.values, s_p.values,
                            alpha=0.13, color="#888888",
                            label="Différence (prétraitement)")
            ax.set_xlabel("Année")
            ax.set_ylabel(metric.capitalize())
            ax.set_title(
                f"Comparaison complet / propre — {metric} par année\n"
                f"(impact du prétraitement et des segments d'exclusion)",
                fontsize=12,
            )
            ax.legend(fontsize=9)
            ax.tick_params(axis="x", rotation=70, labelsize=8)
            ax.grid(True, alpha=0.3)
            plt.tight_layout()
            save_fig(out_dir / f"{num}_comparaison_{metric}.pdf")
    else:
        print("\n── 9. Visualisations comparatives — ignorées "
              "(stats complet absentes)")
    print(f"   Terminé → {out_dir.resolve()}")


if __name__ == "__main__":
    main()
