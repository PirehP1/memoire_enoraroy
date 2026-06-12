#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
  ANALYSE — BOXPLOTS DU NOMBRE D'AUTEURS PAR TOPIC LDA
  Publications présentes dans le réseau de coauteurs
-> but volontairement exploratoire

Pour chaque topic LDA, trace un boxplot horizontal du nombre d'auteurs
des publications présentes dans le réseau de coauteurs. Attribution du
topic par argmax de la matrice gamma.

PRÉ-REQUIS
----------
  python 04_topic_modelling_LDA.py  → output/topic_modelling/gamma_df.csv
  Fichiers réseau (edges_author_pub.csv, nodes_all.csv avec colonne nb_auteurs)

SORTIE  output/boxplots_auteurs/
---------------------------------
  boxplots_auteurs_par_topic.png
  synthese_auteurs_par_topic.csv

DÉPENDANCES
-----------
  pip install pandas numpy networkx matplotlib
"""

import json
import pathlib

import numpy as np
import pandas as pd
import networkx as nx
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

EDGES_PATH = pathlib.Path("data_reseau") / "edges_author_pub.csv"
NODES_PATH = pathlib.Path("data_reseau") / "nodes_all.csv"

# Sorties du pipeline sémantique
CORPUS_PATH = pathlib.Path("output") / "corpus_propre" / "corpus_propre.json"
GAMMA_PATH  = pathlib.Path("output") / "topic_modelling" / "gamma_df.csv"

OUTPUT_DIR = pathlib.Path("output") / "boxplots_auteurs"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

nodes_df = pd.read_csv(NODES_PATH)
edges_df = pd.read_csv(EDGES_PATH)

pub_nodes_df  = nodes_df[nodes_df["Type"] == "publication"].copy()
pub_nodes_set = set(pub_nodes_df["Id"].tolist())

with open(CORPUS_PATH, encoding="utf-8") as f:
    corpus = json.load(f)

corpus_ids    = {i: doc["document"]["doc_id"] for i, doc in enumerate(corpus)}
id_to_index   = {v: k for k, v in corpus_ids.items()}
corpus_id_set = set(corpus_ids.values())

gamma_df   = pd.read_csv(GAMMA_PATH)
doc_col    = gamma_df.columns[0]
topic_cols = [c for c in gamma_df.columns if c != doc_col]
gamma_idx  = gamma_df.set_index(doc_col)


G          = nx.from_pandas_edgelist(edges_df, source="Source", target="Target")
components = sorted(nx.connected_components(G), key=len, reverse=True)
main_cc    = components[0]
other_ccs  = set().union(*components[1:]) if len(components) > 1 else set()

pubs_in_main   = corpus_id_set & {n for n in main_cc   if n in pub_nodes_set}
pubs_in_other  = corpus_id_set & {n for n in other_ccs if n in pub_nodes_set}
pubs_in_reseau = pubs_in_main | pubs_in_other

print(f"Publications du corpus dans le réseau : {len(pubs_in_reseau)}")
print(f"  CCP : {len(pubs_in_main)} | Autres CC : {len(pubs_in_other)}")

rows = []
for doc_id in pubs_in_reseau:
    idx = id_to_index.get(doc_id)
    if idx is None or idx not in gamma_idx.index:
        continue

    topic_maj  = str(gamma_idx.loc[idx].idxmax())

    meta = pub_nodes_df[pub_nodes_df["Id"] == doc_id]
    if meta.empty:
        continue

    nb_aut_raw = meta["nb_auteurs"].values[0]
    try:
        nb_aut = float(nb_aut_raw)
        if np.isnan(nb_aut):
            continue
    except (ValueError, TypeError):
        continue

    rows.append({
        "doc_id"     : doc_id,
        "topic"      : topic_maj,
        "nb_auteurs" : nb_aut,
        "composante" : "CCP" if doc_id in pubs_in_main else "Autres CC",
    })

df = pd.DataFrame(rows)
print(f"\nDocs retenus (nb_auteurs valide) : {len(df)}")
print(df.groupby("topic")["nb_auteurs"].describe().round(2).to_string())

topic_order = sorted(
    df["topic"].unique(),
    key=lambda t: int(t.replace("T", ""))
)
n_topics = len(topic_order)

cmap   = plt.colormaps["tab20"]
colors = {t: cmap(i / max(n_topics - 1, 1)) for i, t in enumerate(topic_order)}

fig_h = max(10, n_topics * 1.35)
fig, axes = plt.subplots(n_topics, 1, figsize=(8, fig_h), sharex=True)

if n_topics == 1:
    axes = [axes]

global_max = df["nb_auteurs"].max()
x_right    = global_max * 1.12

for ax, topic in zip(axes, topic_order):
    data_topic = df[df["topic"] == topic]["nb_auteurs"].dropna()
    n          = len(data_topic)

    # ── Boxplot horizontal ────────────────────────────────────────────
    ax.boxplot(
        data_topic,
        vert=False,
        patch_artist=True,
        widths=0.55,
        notch=False,
        showfliers=True,
        flierprops  =dict(marker="o", markerfacecolor=colors[topic],
                          markeredgecolor="white", markersize=5, alpha=0.6),
        boxprops    =dict(facecolor=colors[topic], alpha=0.75, linewidth=1.2),
        medianprops =dict(color="black", linewidth=2),
        whiskerprops=dict(linewidth=1.2),
        capprops    =dict(linewidth=1.2),
    )

    y_jitter = np.random.uniform(0.75, 1.25, size=n)
    ax.scatter(data_topic, y_jitter, color=colors[topic],
               alpha=0.35, s=14, zorder=3, linewidths=0)

    med  = data_topic.median()
    mean = data_topic.mean()
    q1   = data_topic.quantile(0.25)
    q3   = data_topic.quantile(0.75)
    ax.set_title(
        f"n={n}  méd={med:.1f}  moy={mean:.1f}  [Q1={q1:.1f} – Q3={q3:.1f}]",
        fontsize=7.5, loc="right", color="#444444", pad=2,
    )

    # ── Repère médiane ────────────────────────────────────────────────
    ax.axvline(med, color=colors[topic], linewidth=1, linestyle="--", alpha=0.5)

    # ── Mise en forme du panneau ──────────────────────────────────────
    ax.set_yticks([1])
    ax.set_yticklabels([topic], fontsize=10, fontweight="bold")
    ax.set_ylim(0.4, 1.6)
    ax.set_xlim(0, x_right)
    ax.tick_params(axis="x", labelsize=8)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.grid(axis="x", linestyle=":", linewidth=0.7, alpha=0.6)
    ax.set_facecolor("#f7f7f7" if topic_order.index(topic) % 2 == 0 else "white")

axes[-1].set_xlabel("Nombre d'auteurs", fontsize=10)

fig.suptitle(
    "Distribution du nombre d'auteurs par topic LDA\n"
    "(publications présentes dans le réseau de coauteurs — topic majoritaire)",
    fontsize=12, fontweight="bold", y=1.01,
)

fig.text(
    0.5, -0.015,
    f"Publications dans le réseau : {len(df)}  "
    f"(CCP : {len(pubs_in_main)} | Autres CC : {len(pubs_in_other)})\n"
    "Topics ordonnés numériquement (T0, T1…).",
    ha="center", fontsize=8, color="#555555",
)

plt.tight_layout()

out_path = OUTPUT_DIR / "boxplots_auteurs_par_topic.png"
fig.savefig(out_path, dpi=180, bbox_inches="tight")
plt.close(fig)
print(f"\n✓ Planche sauvegardée : {out_path}")

synthese = (
    df.groupby("topic")["nb_auteurs"]
    .agg(n="count", mediane="median", moyenne="mean",
         q1=lambda x: x.quantile(0.25),
         q3=lambda x: x.quantile(0.75),
         min="min", max="max")
    .round(2)
    .reindex(topic_order)
)
csv_path = OUTPUT_DIR / "synthese_auteurs_par_topic.csv"
synthese.to_csv(csv_path, encoding="utf-8-sig")
print(f"✓ Synthèse CSV : {csv_path}")
print()
print(synthese.to_string())
