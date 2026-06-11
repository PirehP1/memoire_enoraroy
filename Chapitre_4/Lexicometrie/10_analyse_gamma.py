#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
  SCRIPT 10 — ANALYSE DE LA DISTRIBUTION THÉMATIQUE (MATRICE GAMMA)

Lit les fichiers CSV produits par 07_LDA_k.py et produit trois
graphiques d'analyse de la matrice γ (documents × topics) :

  I.   Concentration thématique → entropie de γ par document
  II.  Topic dominant           → nb de documents par topic (argmax)
  III. Corrélations             → heatmap Pearson entre topics

Approche : distributions continues sans seuil de présence arbitraire,
conforme à Griffiths & Steyvers (2004).

SORTIES
-------
  output/topic_modelling/
    07_concentration_thematique.pdf
    08_topic_dominant.pdf
    09_correlation_topics.pdf
    analyse_gamma.txt               ← bilan chiffré

STRUCTURE ATTENDUE
------------------
  <dossier du script>/
  └── output/topic_modelling/
      ├── gamma_df.csv        ← produit par 07_LDA_k.py
      └── topics_lda.csv      ← produit par 07_LDA_k.py

PRÉ-REQUIS
----------
  python 07_LDA_k.py

DÉPENDANCES
-----------
  pip install numpy pandas matplotlib seaborn scipy
"""

import pathlib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.stats import entropy as scipy_entropy

BASE_DIR   = pathlib.Path(__file__).resolve().parent
OUT_DIR    = BASE_DIR / "output" / "topic_modelling"
GAMMA_CSV  = OUT_DIR / "gamma_df.csv"
TOPICS_CSV = OUT_DIR / "topics_lda.csv"


if __name__ == "__main__":

    for f in [GAMMA_CSV, TOPICS_CSV]:
        if not f.exists():
            print(f"[ERREUR] Fichier introuvable : {f}")
            print("→ Lancez d'abord 07_LDA_k.py")
            exit()

    gamma_df  = pd.read_csv(GAMMA_CSV, index_col=0)
    df_topics = pd.read_csv(TOPICS_CSV)

    topic_cols = [c for c in gamma_df.columns if c.startswith("T")]
    num_topics = len(topic_cols)
    H_max      = np.log(num_topics)

    # Labels courts : "T0 — mot1 / mot2 / mot3"
    labels = {}
    for tid, col in enumerate(topic_cols):
        mots = " / ".join(df_topics[df_topics["topic_id"] == tid].head(3)["mot"])
        labels[col] = f"{col} — {mots}"

    print(f"  {len(gamma_df)} documents | {num_topics} topics")

    lines = [
        "ANALYSE DE LA MATRICE GAMMA",
        "=" * 60,
        f"Nb de documents : {len(gamma_df)}",
        f"Nb de topics    : {num_topics}",
        f"Approche        : distributions continues (pas de seuil),",
        f"                  conforme à Griffiths & Steyvers (2004)",
        "",
    ]

    # ──────────────────────────────────────────────────────────────────
    #  I. CONCENTRATION THÉMATIQUE — entropie de γ par document
    # ──────────────────────────────────────────────────────────────────
    print("\n── I. CONCENTRATION THÉMATIQUE ───────────────────────────────")

    doc_entropy      = gamma_df[topic_cols].apply(
        lambda row: scipy_entropy(row.values), axis=1
    )
    doc_entropy_norm = doc_entropy / H_max

    desc = doc_entropy_norm.describe()
    lines += [
        "I. CONCENTRATION THÉMATIQUE (entropie normalisée de γ)",
        "  H/H_max = 0 : document concentré sur 1 seul topic",
        f"  H/H_max = 1 : distribution uniforme sur les {num_topics} topics",
        "",
        f"  Moyenne   : {desc['mean']:.3f}",
        f"  Médiane   : {desc['50%']:.3f}",
        f"  Min / Max : {desc['min']:.3f} / {desc['max']:.3f}",
        "",
    ]
    if desc["mean"] < 0.4:
        lines.append("  → Documents majoritairement concentrés : corpus thématiquement structuré.")
    elif desc["mean"] > 0.7:
        lines.append("  → Documents très dispersés : forte hybridité thématique ou k trop élevé.")
    else:
        lines.append("  → Dispersion modérée : mélange de documents concentrés et hybrides.")
    lines.append("")

    print(f"  Moyenne : {desc['mean']:.3f} | Médiane : {desc['50%']:.3f}")

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(doc_entropy_norm, bins=40, color="#2c7bb6", edgecolor="white")
    ax.axvline(desc["mean"], color="#d7191c", ls="--", lw=1.8,
               label=f"Moyenne = {desc['mean']:.3f}")
    ax.axvline(desc["50%"], color="#fdae61", ls="--", lw=1.8,
               label=f"Médiane = {desc['50%']:.3f}")
    ax.set_xlabel("Entropie normalisée de γ  (0 = concentré, 1 = uniforme)", fontsize=11)
    ax.set_ylabel("Nombre de documents", fontsize=11)
    ax.set_title("Concentration thématique des documents\n"
                 "(entropie de Shannon sur γ, sans seuil)", fontsize=12)
    ax.legend(fontsize=10)
    ax.grid(axis="y", alpha=0.3, ls=":")
    plt.tight_layout()
    plt.savefig(OUT_DIR / "07_concentration_thematique.pdf",
                format="pdf", bbox_inches="tight")
    plt.close()
    print("  → 07_concentration_thematique.pdf")

    # ──────────────────────────────────────────────────────────────────
    #  II. TOPIC DOMINANT PAR DOCUMENT (argmax de γ)
    # ──────────────────────────────────────────────────────────────────

    gamma_df["topic_dominant"] = gamma_df[topic_cols].idxmax(axis=1)
    gamma_df["gamma_dominant"] = gamma_df[topic_cols].max(axis=1)
    dominant_counts = gamma_df["topic_dominant"].value_counts().reindex(topic_cols, fill_value=0)
    gamma_dom_mean  = gamma_df["gamma_dominant"].mean()

    lines += [
        "II. TOPIC DOMINANT PAR DOCUMENT (argmax de γ)",
        "  (topic avec le γ le plus élevé pour chaque document)",
        "",
    ]
    for col, n in dominant_counts.items():
        pct       = 100 * n / len(gamma_df)
        moy_gamma = gamma_df.loc[gamma_df["topic_dominant"] == col, "gamma_dominant"].mean()
        lines.append(
            f"  {labels[col]:<55}  {n:>5} docs  ({pct:.1f} %)  γ dom. moy.={moy_gamma:.3f}"
        )
    lines += [
        "",
        f"  γ moyen du topic dominant (tous docs) : {gamma_dom_mean:.3f}",
        f"  (proche de 1 = docs bien concentrés ; "
        f"proche de {1/num_topics:.2f} = distribution uniforme)",
        "",
    ]
    print(dominant_counts.to_string())
    print(f"  γ moyen du topic dominant : {gamma_dom_mean:.3f}")

    palette = (sns.color_palette("tab10", num_topics) if num_topics <= 10
               else sns.color_palette("tab20", num_topics))

    fig, ax = plt.subplots(figsize=(10, 5))
    bars = ax.bar(range(num_topics), dominant_counts.values,
                  color=palette, edgecolor="white")
    ax.set_xticks(range(num_topics))
    ax.set_xticklabels([labels[c] for c in topic_cols],
                       rotation=40, ha="right", fontsize=8)
    ax.set_ylabel("Nombre de documents", fontsize=11)
    ax.set_title("Documents par topic dominant (argmax de γ)", fontsize=12)
    ax.grid(axis="y", alpha=0.3, ls=":")
    for bar, val in zip(bars, dominant_counts.values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                str(val), ha="center", va="bottom", fontsize=8)
    plt.tight_layout()
    plt.savefig(OUT_DIR / "08_topic_dominant.pdf",
                format="pdf", bbox_inches="tight")
    plt.close()
    print("  → 08_topic_dominant.pdf")

    # ──────────────────────────────────────────────────────────────────
    #  III. CORRÉLATIONS ENTRE TOPICS (Pearson sur γ continu)
    # ──────────────────────────────────────────────────────────────────
    print("\n── III. CORRÉLATIONS ENTRE TOPICS ────────────────────────────")

    corr = gamma_df[topic_cols].corr()
    corr_pairs = (
        corr.where(np.triu(np.ones(corr.shape), k=1).astype(bool))
            .stack().reset_index()
    )
    corr_pairs.columns = ["topic_a", "topic_b", "correlation"]
    corr_pairs = corr_pairs.reindex(
        corr_pairs["correlation"].abs().sort_values(ascending=False).index
    )

    lines += [
        "III. CORRÉLATIONS ENTRE TOPICS (Pearson sur γ continu)",
        "  5 paires les plus corrélées positivement :",
    ]
    for _, row in corr_pairs[corr_pairs["correlation"] > 0].head(5).iterrows():
        lines.append(
            f"    {labels[row['topic_a']]}  ↔  {labels[row['topic_b']]}  r={row['correlation']:.3f}"
        )
    lines += ["", "  5 paires les plus corrélées négativement :"]
    for _, row in corr_pairs[corr_pairs["correlation"] < 0].tail(5).iterrows():
        lines.append(
            f"    {labels[row['topic_a']]}  ↔  {labels[row['topic_b']]}  r={row['correlation']:.3f}"
        )
    lines += [
        "",
        "  Lecture :",
        "    r fort positif → topics co-occurrents (souvent dans les mêmes docs)",
        "    r fort négatif → topics exclusifs (docs spécialisés sur l'un ou l'autre)",
        "    r proche de 0  → topics indépendants",
        "",
    ]

    short_labels = [f"T{i}" for i in range(num_topics)]
    fig, ax = plt.subplots(figsize=(max(8, num_topics * 0.7),
                                    max(6, num_topics * 0.6)))
    mask = np.triu(np.ones_like(corr, dtype=bool))
    sns.heatmap(corr, mask=mask, annot=True, fmt=".2f",
                cmap="RdBu_r", center=0, vmin=-1, vmax=1,
                square=True, linewidths=0.5, ax=ax,
                xticklabels=short_labels,
                yticklabels=[labels[c] for c in topic_cols],
                annot_kws={"size": 7})
    ax.set_title("Corrélations entre topics (Pearson sur γ continu)", fontsize=12)
    ax.tick_params(axis="y", labelsize=8)
    ax.tick_params(axis="x", labelsize=9)
    plt.tight_layout()
    plt.savefig(OUT_DIR / "09_correlation_topics.pdf",
                format="pdf", bbox_inches="tight")
    plt.close()
    print("  → 09_correlation_topics.pdf")

    (OUT_DIR / "analyse_gamma.txt").write_text("\n".join(lines), encoding="utf-8")
    print("\n  → analyse_gamma.txt")

    print(f"\n✓ Terminé — {num_topics} topics | {len(gamma_df)} documents")
