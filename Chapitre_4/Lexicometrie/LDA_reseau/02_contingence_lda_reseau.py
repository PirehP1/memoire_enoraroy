"""
  SCRIPT 02 — LDA × RÉSEAU : ANALYSE DE SUR/SOUS-REPRÉSENTATION

Deux tableaux de contingence topics × appartenance au réseau :

  T1 — topic | hors réseau | dans réseau (CCP + autres CC)
       → teste si les topics sont sur/sous-représentés dans le réseau
         par rapport au corpus propre complet

  T2 — topic | dans CCP | dans autres CC
       → (uniquement pubs dans le réseau) teste si les topics varient
         entre composantes connexes

Deux modes d'attribution de topic :
  A. "majority"  — un seul topic par doc (argmax de gamma)
  B. "threshold" — plusieurs topics si gamma >= GAMMA_THRESHOLD

SORTIES
-------
  output/
    contingence_T1_majority.csv / _threshold.csv
    contingence_T2_majority.csv / _threshold.csv
    residus_T1_majority.csv     / _threshold.csv  ← résidus de Pearson
    residus_T2_majority.csv     / _threshold.csv
    contrib_T1_majority.csv     / _threshold.csv  ← contributions au χ²
    contrib_T2_majority.csv     / _threshold.csv
    heatmap_T1_majority.png     / _threshold.png
    heatmap_T2_majority.png     / _threshold.png
    recapitulatif_khi2.csv
    rapport_statistiques.txt

STRUCTURE ATTENDUE
------------------
  lda_reseau/
  ├── data/
  │   ├── edges_author_pub.csv
  │   └── nodes_all.csv
  └── output/   ← créé automatiquement

  Fichiers LDA lus depuis le dossier parent :
  ├── ../output/corpus_propre/corpus_propre.json
  └── ../output/topic_modelling/gamma_df.csv


PRÉ-REQUIS
----------
  07_LDA_k.py  → ../output/topic_modelling/gamma_df.csv

DÉPENDANCES
-----------
  pip install pandas networkx numpy matplotlib seaborn scipy
=======================================================================
"""

import json
import sys
import warnings
import pathlib

import numpy as np
import pandas as pd
import networkx as nx
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.stats import chi2_contingency

warnings.filterwarnings("ignore")

BASE_DIR = pathlib.Path(__file__).resolve().parent

EDGES_PATH  = BASE_DIR / "data" / "edges_author_pub.csv"
NODES_PATH  = BASE_DIR / "data" / "nodes_all.csv"
CORPUS_PATH = BASE_DIR.parent / "output" / "corpus_propre" / "corpus_propre.json"
GAMMA_PATH  = BASE_DIR.parent / "output" / "topic_modelling" / "gamma_df.csv"

OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

GAMMA_THRESHOLD = 0.15  # seuil pour le mode "threshold"

rapport_lignes = []


def rlog(msg=""):
    print(msg)
    rapport_lignes.append(str(msg))



for p in [EDGES_PATH, NODES_PATH, CORPUS_PATH, GAMMA_PATH]:
    if not p.exists():
        print(f"[ERREUR] Fichier introuvable : {p}")
        sys.exit(1)

edges_df      = pd.read_csv(EDGES_PATH)
nodes_df      = pd.read_csv(NODES_PATH)
pub_nodes_set = set(nodes_df[nodes_df["Type"] == "publication"]["Id"].tolist())

with open(CORPUS_PATH, encoding="utf-8") as f:
    corpus = json.load(f)

corpus_ids    = {i: doc["document"]["doc_id"] for i, doc in enumerate(corpus)}
corpus_id_set = set(corpus_ids.values())
id_to_index   = {v: k for k, v in corpus_ids.items()}

gamma_df      = pd.read_csv(GAMMA_PATH)
doc_col       = gamma_df.columns[0]
topic_cols    = [c for c in gamma_df.columns if c != doc_col]
gamma_indexed = gamma_df.set_index(doc_col)

rlog(f"Corpus propre           : {len(corpus_id_set)} publications")
rlog(f"Nœuds 'publication'     : {len(pub_nodes_set)}")
rlog(f"Gamma — {len(topic_cols)} topics : {topic_cols}")
rlog()



G = nx.from_pandas_edgelist(edges_df, source="Source", target="Target")
components = sorted(nx.connected_components(G), key=len, reverse=True)
main_cc    = components[0]
other_ccs  = set().union(*components[1:]) if len(components) > 1 else set()

pubs_in_main     = corpus_id_set & {n for n in main_cc   if n in pub_nodes_set}
pubs_in_other    = corpus_id_set & {n for n in other_ccs if n in pub_nodes_set}
pubs_in_reseau   = pubs_in_main | pubs_in_other
pubs_hors_reseau = corpus_id_set - pubs_in_reseau

rlog(f"Graphe : {G.number_of_nodes()} nœuds, {G.number_of_edges()} arêtes")
rlog(f"Composante principale   : {len(main_cc)} nœuds")
rlog(f"Autres composantes      : {len(components)-1} ({len(other_ccs)} nœuds)")
rlog()
rlog(f"Publications corpus dans le réseau (CCP+autres) : {len(pubs_in_reseau)}")
rlog(f"  dont dans la CCP      : {len(pubs_in_main)}")
rlog(f"  dont dans autres CC   : {len(pubs_in_other)}")
rlog(f"Publications corpus HORS réseau                 : {len(pubs_hors_reseau)}")
rlog()


def get_topics(doc_id: str, mode: str) -> list:
    """Retourne la liste des topics pour un doc selon le mode."""
    idx = id_to_index.get(doc_id)
    if idx is None or idx not in gamma_indexed.index:
        return []
    row = gamma_indexed.loc[idx]
    if mode == "majority":
        return [str(row.idxmax())]
    else:  # threshold
        dominant = row[row >= GAMMA_THRESHOLD]
        return ([str(t) for t in dominant.index.tolist()]
                if not dominant.empty else [str(row.idxmax())])


def build_contingency(set_col1: set, set_col2: set,
                      col1_name: str, col2_name: str, mode: str) -> pd.DataFrame:
    """
    Construit un tableau de contingence topics × [col1, col2].
    set_col1 et set_col2 sont des ensembles de doc_id disjoints.
    """
    counts = {t: {col1_name: 0, col2_name: 0} for t in topic_cols}

    for doc_id in set_col1:
        for t in get_topics(doc_id, mode):
            if t in counts:
                counts[t][col1_name] += 1

    for doc_id in set_col2:
        for t in get_topics(doc_id, mode):
            if t in counts:
                counts[t][col2_name] += 1

    df = pd.DataFrame(counts).T
    df.index.name = "topic"
    df["TOTAL"] = df[col1_name] + df[col2_name]
    return df.sort_index()


def analyse_contingence(ct: pd.DataFrame, titre: str, mode: str, tag: str):
    """
    Khi², résidus de Pearson, contributions au χ², heatmap.
    """
    cols_data = [c for c in ct.columns if c != "TOTAL"]
    obs = ct[cols_data].values.astype(float)

    chi2, p, dof, expected = chi2_contingency(obs)
    cramers_n = obs.sum()
    cramers_v = np.sqrt(chi2 / (cramers_n * (min(obs.shape) - 1)))

    rlog(f"── {titre} [{mode}] ──")
    rlog(f"   χ²  = {chi2:.4f}  |  ddl = {dof}  |  p = {p:.6f}")
    rlog(f"   V de Cramér = {cramers_v:.4f}  (N={int(cramers_n)})")
    if p < 0.001:
        rlog("   *** Résultat très significatif (p < 0,001)")
    elif p < 0.01:
        rlog("   **  Résultat significatif (p < 0,01)")
    elif p < 0.05:
        rlog("   *   Résultat significatif (p < 0,05)")
    else:
        rlog("   ns  Résultat non significatif (p ≥ 0,05)")
    rlog()

    # Résidus standardisés de Pearson : (obs - exp) / sqrt(exp)
    with np.errstate(divide="ignore", invalid="ignore"):
        residus = np.where(expected > 0, (obs - expected) / np.sqrt(expected), 0)
    residus_df = pd.DataFrame(residus, index=ct.index, columns=cols_data)
    residus_df.index.name = "topic"

    # Contributions au χ² en % : (obs - exp)² / exp / chi² × 100
    with np.errstate(divide="ignore", invalid="ignore"):
        contrib = np.where(expected > 0,
                           ((obs - expected) ** 2 / expected) / chi2 * 100, 0)
    contrib_df = pd.DataFrame(contrib, index=ct.index, columns=cols_data)
    contrib_df.index.name = "topic"

    # Export CSV
    ct.to_csv(OUTPUT_DIR / f"contingence_{tag}_{mode}.csv", encoding="utf-8-sig")
    residus_df.round(4).to_csv(OUTPUT_DIR / f"residus_{tag}_{mode}.csv",
                                encoding="utf-8-sig")
    contrib_df.round(4).to_csv(OUTPUT_DIR / f"contrib_{tag}_{mode}.csv",
                                encoding="utf-8-sig")

    # Heatmap résidus + contributions
    fig, axes = plt.subplots(1, 2, figsize=(14, max(6, len(ct) * 0.55)))
    vmax = max(2.0, np.abs(residus).max())

    sns.heatmap(
        residus_df, ax=axes[0],
        cmap="RdBu_r", center=0, vmin=-vmax, vmax=vmax,
        annot=True, fmt=".2f", linewidths=0.5,
        cbar_kws={"label": "Résidu de Pearson"},
    )
    axes[0].set_title(f"Résidus standardisés de Pearson\n{titre}\n[mode : {mode}]",
                      fontsize=10)
    axes[0].set_xlabel("")
    axes[0].set_ylabel("Topic")

    sns.heatmap(
        contrib_df, ax=axes[1],
        cmap="YlOrRd",
        annot=True, fmt=".1f", linewidths=0.5,
        cbar_kws={"label": "Contribution au χ² (%)"},
    )
    axes[1].set_title(f"Contributions au χ² (%)\n{titre}\n[mode : {mode}]",
                      fontsize=10)
    axes[1].set_xlabel("")
    axes[1].set_ylabel("")

    plt.suptitle(
        f"χ²={chi2:.2f}, p={p:.4f}, V de Cramér={cramers_v:.3f}  (N={int(cramers_n)})",
        fontsize=9, y=1.01,
    )
    plt.tight_layout()
    fig.savefig(OUTPUT_DIR / f"heatmap_{tag}_{mode}.png", dpi=150, bbox_inches="tight")
    plt.close(fig)

    return chi2, p, dof, cramers_v, residus_df, contrib_df


summary_rows = []

for mode in ("majority", "threshold"):
    rlog("=" * 65)
    rlog(f"  MODE : {mode.upper()}")
    rlog("=" * 65)
    rlog()

    # T1 : corpus propre complet vs réseau
    ct_T1 = build_contingency(
        pubs_hors_reseau, pubs_in_reseau,
        "hors_reseau", "dans_reseau", mode,
    )
    rlog("Tableau T1 — Corpus × Réseau")
    rlog(ct_T1.to_string())
    rlog()

    chi2_T1, p_T1, dof_T1, v_T1, _, _ = analyse_contingence(
        ct_T1, titre="T1 : Corpus propre  vs  Réseau", mode=mode, tag="T1",
    )

    # T2 : CCP vs autres CC (uniquement pubs dans le réseau)
    ct_T2 = build_contingency(
        pubs_in_main, pubs_in_other,
        "CCP", "autres_CC", mode,
    )
    rlog("Tableau T2 — CCP × Autres composantes (pubs dans le réseau)")
    rlog(ct_T2.to_string())
    rlog()

    chi2_T2, p_T2, dof_T2, v_T2, _, _ = analyse_contingence(
        ct_T2, titre="T2 : CCP  vs  Autres CC", mode=mode, tag="T2",
    )

    summary_rows += [
        {"mode": mode, "tableau": "T1", "chi2": round(chi2_T1, 4),
         "p": round(p_T1, 6), "dof": dof_T1, "V_Cramer": round(v_T1, 4)},
        {"mode": mode, "tableau": "T2", "chi2": round(chi2_T2, 4),
         "p": round(p_T2, 6), "dof": dof_T2, "V_Cramer": round(v_T2, 4)},
    ]
    rlog()



summary_df = pd.DataFrame(summary_rows)
rlog(summary_df.to_string(index=False))
rlog()
rlog(f"Dossier de sortie : {OUTPUT_DIR}")

summary_df.to_csv(OUTPUT_DIR / "recapitulatif_khi2.csv", index=False, encoding="utf-8-sig")

with open(OUTPUT_DIR / "rapport_statistiques.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(rapport_lignes))

print(f"\n Analyse terminée. Tous les fichiers sont dans : {OUTPUT_DIR}")
