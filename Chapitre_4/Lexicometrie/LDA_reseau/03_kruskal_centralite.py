"""
  SCRIPT 03 — KRUSKAL-WALLIS : TOPIC LDA × CENTRALITÉ

Pour chaque indicateur de centralité et chaque sous-corpus (réseau
entier / CCP seule), teste si les distributions diffèrent selon le
topic LDA dominant.

  H0 : les distributions de centralité sont identiques entre tous
       les topics
  H1 : au moins un topic présente une distribution différente

SORTIES
-------
  output/kruskal/
    kruskal_summary.csv              ← récapitulatif de tous les tests
    heatmap_kruskal_synthese.png     ← heatmap p-values et ε²
    rapport_kruskal.txt

STRUCTURE ATTENDUE
------------------
  lda_reseau/
  ├── data/
  │   ├── edges_author_pub.csv
  │   └── metriques_reseau_bip.csv
  └── output/kruskal/   ← créé automatiquement

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
import pathlib

import numpy as np
import pandas as pd
import networkx as nx
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.stats import kruskal


BASE_DIR = pathlib.Path(__file__).resolve().parent

METRICS_PATH = BASE_DIR / "data" / "metriques_reseau_bip.csv"
EDGES_PATH   = BASE_DIR / "data" / "edges_author_pub.csv"
CORPUS_PATH  = BASE_DIR.parent / "output" / "corpus_propre" / "corpus_propre.json"
GAMMA_PATH   = BASE_DIR.parent / "output" / "topic_modelling" / "gamma_df.csv"

OUTPUT_DIR = BASE_DIR / "output" / "kruskal"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

ALPHA = 0.05

CENTRALITY_COLS = [
    "degree",
    "weighted degree",
    "betweenesscentrality",
    "eigencentrality",
    "closnesscentrality",
    "harmonicclosnesscentrality",
]

rapport = []


def rlog(msg=""):
    print(msg)
    rapport.append(str(msg))


for p in [METRICS_PATH, EDGES_PATH, CORPUS_PATH, GAMMA_PATH]:
    if not p.exists():
        print(f"[ERREUR] Fichier introuvable : {p}")
        sys.exit(1)

metrics_df  = pd.read_csv(METRICS_PATH, low_memory=False)
pub_metrics = metrics_df[metrics_df["type"] == "publication"].copy()
rlog(f"\nPublications dans le fichier de métriques : {len(pub_metrics)}")

with open(CORPUS_PATH, encoding="utf-8") as f:
    corpus = json.load(f)
corpus_ids    = {i: doc["document"]["doc_id"] for i, doc in enumerate(corpus)}
id_to_index   = {v: k for k, v in corpus_ids.items()}
corpus_id_set = set(corpus_ids.values())

gamma_df       = pd.read_csv(GAMMA_PATH)
doc_col        = gamma_df.columns[0]
topic_cols_lda = [c for c in gamma_df.columns if c != doc_col]
gamma_idx      = gamma_df.set_index(doc_col)


def majority_topic(doc_id):
    idx = id_to_index.get(doc_id)
    if idx is None or idx not in gamma_idx.index:
        return None
    return str(gamma_idx.loc[idx].idxmax())


pub_metrics = pub_metrics.copy()
pub_metrics["topic_lda"] = pub_metrics["Id"].map(majority_topic)
pub_metrics = pub_metrics[pub_metrics["topic_lda"].notna()].copy()
rlog(f"Publications avec topic LDA (corpus propre ∩ réseau) : {len(pub_metrics)}")


# ──────────────────────────────────────────────────────────────────────
#  2. COMPOSANTE CONNEXE PRINCIPALE
# ──────────────────────────────────────────────────────────────────────

edges_df   = pd.read_csv(EDGES_PATH)
G          = nx.from_pandas_edgelist(edges_df, source="Source", target="Target")
components = sorted(nx.connected_components(G), key=len, reverse=True)
main_cc    = components[0]

pub_metrics["dans_ccp"] = pub_metrics["Id"].isin(main_cc)
rlog(f"  dont dans la CCP        : {pub_metrics['dans_ccp'].sum()}")
rlog(f"  dont hors CCP           : {(~pub_metrics['dans_ccp']).sum()}")
rlog()


# ──────────────────────────────────────────────────────────────────────
#  3. NETTOYAGE DES COLONNES DE CENTRALITÉ
# ──────────────────────────────────────────────────────────────────────

for col in CENTRALITY_COLS:
    if col in pub_metrics.columns:
        pub_metrics[col] = pd.to_numeric(pub_metrics[col], errors="coerce")

avail_cols = [c for c in CENTRALITY_COLS if c in pub_metrics.columns]
rlog(f"Indicateurs de centralité disponibles : {avail_cols}")


# ──────────────────────────────────────────────────────────────────────
#  4. KRUSKAL-WALLIS
# ──────────────────────────────────────────────────────────────────────

def epsilon_squared(H, n):
    """Taille d'effet ε² pour Kruskal-Wallis."""
    denom = (n ** 2 - 1) / (n + 1)
    return H / denom if denom > 0 else np.nan


def run_kruskal(data: pd.DataFrame, metric: str, scope_label: str):
    """Exécute le test KW pour un indicateur et un sous-corpus."""
    sub          = data[["topic_lda", metric]].dropna()
    groups_valid = [(name, grp) for name, grp in sub.groupby("topic_lda")
                    if len(grp) >= 2]

    if len(groups_valid) < 2:
        return None

    names  = [g[0] for g in groups_valid]
    arrays = [g[1][metric].values for g in groups_valid]

    H, p  = kruskal(*arrays)
    n     = sub.shape[0]
    k     = len(arrays)
    eps2  = epsilon_squared(H, n)
    sig   = ("***" if p < 0.001 else ("**" if p < 0.01
             else ("*" if p < 0.05 else "ns")))

    rlog(f"  [{scope_label}] {metric:35s}  H={H:.3f}  p={p:.5f} {sig}"
         f"  ε²={eps2:.3f}  (n={n}, k={k})")

    return {
        "scope"  : scope_label,
        "metric" : metric,
        "H"      : round(H, 4),
        "p"      : round(p, 6),
        "sig"    : sig,
        "eps2"   : round(eps2, 4),
        "n"      : n,
        "k"      : k,
    }


# ──────────────────────────────────────────────────────────────────────
#  5. BOUCLE SUR LES DEUX SCOPES
# ──────────────────────────────────────────────────────────────────────

scopes = {
    "reseau_entier": pub_metrics,
    "CCP_seule"    : pub_metrics[pub_metrics["dans_ccp"]],
}

all_results = []

for scope_label, df_scope in scopes.items():
    rlog()
    rlog(f"── Scope : {scope_label}  (n={len(df_scope)}) ──")
    for metric in avail_cols:
        res = run_kruskal(df_scope, metric, scope_label)
        if res:
            all_results.append(res)

summary_df = pd.DataFrame(all_results)
summary_df.to_csv(OUTPUT_DIR / "kruskal_summary.csv", index=False, encoding="utf-8-sig")
rlog()
rlog("─" * 65)
rlog("RÉCAPITULATIF")
rlog(summary_df[["scope", "metric", "H", "p", "sig", "eps2", "n", "k"]].to_string(index=False))


# ──────────────────────────────────────────────────────────────────────
#  6. HEATMAPS RÉCAPITULATIVES
# ──────────────────────────────────────────────────────────────────────

def make_summary_heatmaps(summary: pd.DataFrame):
    scopes_u  = summary["scope"].unique()
    metrics_u = summary["metric"].unique()

    pval_mat = pd.DataFrame(index=metrics_u, columns=scopes_u, dtype=float)
    eps_mat  = pd.DataFrame(index=metrics_u, columns=scopes_u, dtype=float)

    for _, row in summary.iterrows():
        pval_mat.loc[row["metric"], row["scope"]] = row["p"]
        eps_mat.loc[row["metric"],  row["scope"]] = row["eps2"]

    fig, axes = plt.subplots(1, 2, figsize=(10, max(4, len(metrics_u) * 0.7)))

    log_p = -np.log10(pval_mat.astype(float).clip(lower=1e-10))
    sns.heatmap(
        log_p, ax=axes[0], cmap="YlOrRd",
        annot=pval_mat.map(lambda v: f"{v:.4f}").values,
        fmt="", linewidths=0.5,
        cbar_kws={"label": "−log₁₀(p)"},
    )
    axes[0].set_title("p-values (−log₁₀)\n[seuil α=0,05 ≈ 1.30]", fontsize=9)

    sns.heatmap(
        eps_mat.astype(float), ax=axes[1], cmap="Blues",
        annot=True, fmt=".3f", linewidths=0.5,
        cbar_kws={"label": "ε² (taille d'effet)"},
    )
    axes[1].set_title("Taille d'effet ε²\n[≥0.01 petit  ≥0.06 moyen  ≥0.14 grand]",
                      fontsize=9)

    plt.suptitle("Kruskal-Wallis : topic LDA × centralité", fontweight="bold")
    plt.tight_layout()
    fig.savefig(OUTPUT_DIR / "heatmap_kruskal_synthese.png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    rlog(f"\n✓ Heatmap synthèse → heatmap_kruskal_synthese.png")


make_summary_heatmaps(summary_df)

rlog(f"\nTous les fichiers : {OUTPUT_DIR}")

with open(OUTPUT_DIR / "rapport_kruskal.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(rapport))

print(f"\n✓ Analyse terminée. Fichiers dans : {OUTPUT_DIR}")
