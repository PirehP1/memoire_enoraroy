"""
  SCRIPT 01 — CROISEMENT CORPUS PROPRE × RÉSEAU × TOPICS LDA

Analyse corpus propre × composantes connexes du réseau ×
topics LDA.

  1. Charge les arêtes et nœuds du réseau (export Gephi)
  2. Identifie la composante connexe principale (CCP) et les autres
  3. Croise avec le corpus propre (publications avec fulltext)
  4. Associe à chaque publication son/ses topic(s) LDA dominant(s)
     via gamma_df.csv

SORTIES
-------
  output/
    publications_ccp_topics_lda.csv       ← publications dans la CCP
    publications_autres_cc_topics_lda.csv ← publications dans les autres CC

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
  pip install pandas networkx
"""

import json
import sys
import pathlib

import pandas as pd
import networkx as nx

BASE_DIR = pathlib.Path(__file__).resolve().parent

EDGES_PATH = BASE_DIR / "data" / "edges_author_pub.csv"
NODES_PATH = BASE_DIR / "data" / "nodes_all.csv"

# Données LDA — lues depuis le dossier parent de la partie lexico
CORPUS_PATH = BASE_DIR.parent / "output" / "corpus_propre" / "corpus_propre.json"
GAMMA_PATH  = BASE_DIR.parent / "output" / "topic_modelling" / "gamma_df.csv"

OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
GAMMA_THRESHOLD = 0.15


for p in [EDGES_PATH, NODES_PATH, CORPUS_PATH, GAMMA_PATH]:
    if not p.exists():
        print(f"[ERREUR] Fichier introuvable : {p}")
        sys.exit(1)

edges_df = pd.read_csv(EDGES_PATH)
nodes_df = pd.read_csv(NODES_PATH)

pub_nodes     = nodes_df[nodes_df["Type"] == "publication"]["Id"].tolist()
pub_nodes_set = set(pub_nodes)
print(f"\n  • {len(pub_nodes)} nœuds de type publication dans nodes_all.csv")

with open(CORPUS_PATH, encoding="utf-8") as f:
    corpus = json.load(f)

corpus_ids    = {i: doc["document"]["doc_id"] for i, doc in enumerate(corpus)}
corpus_id_set = set(corpus_ids.values())
id_to_index   = {v: k for k, v in corpus_ids.items()}
print(f"  • {len(corpus_id_set)} publications dans le corpus propre (fulltext disponible)")

gamma_df = pd.read_csv(GAMMA_PATH)
print(f"  • gamma_df : {gamma_df.shape[0]} lignes × {gamma_df.shape[1]} colonnes")

doc_col       = gamma_df.columns[0]
topic_cols    = [c for c in gamma_df.columns if c != doc_col]
gamma_indexed = gamma_df.set_index(doc_col)


print("\n── Construction du graphe ────────────────────────────────────")

G = nx.from_pandas_edgelist(edges_df, source="Source", target="Target")
print(f"  • Nœuds : {G.number_of_nodes()} | Arêtes : {G.number_of_edges()}")

components = sorted(nx.connected_components(G), key=len, reverse=True)
main_cc    = components[0]
other_ccs  = components[1:]

print(f"  • Composante connexe principale : {len(main_cc)} nœuds")
print(f"  • Autres composantes            : {len(other_ccs)} "
      f"({sum(len(c) for c in other_ccs)} nœuds au total)")

if other_ccs:
    sizes = [len(c) for c in other_ccs]
    print(f"    → Tailles : min={min(sizes)}, max={max(sizes)}, "
          f"médiane={sorted(sizes)[len(sizes)//2]}")


def build_results(cc_nodes: set, label: str) -> pd.DataFrame:
    """
    Pour un ensemble de nœuds du réseau, retourne un DataFrame des
    publications du corpus propre présentes dans cet ensemble, enrichi
    des topics LDA dominants (gamma >= GAMMA_THRESHOLD).
    """
    pubs_in_cc        = {n for n in cc_nodes if n in pub_nodes_set}
    pubs_corpus_in_cc = corpus_id_set & pubs_in_cc

    print(f"\n  [{label}]")
    print(f"    Publications 'publication' dans la composante : {len(pubs_in_cc)}")
    print(f"    Publications du corpus propre                 : {len(pubs_corpus_in_cc)}")

    rows = []
    for doc_id in sorted(pubs_corpus_in_cc):
        idx = id_to_index.get(doc_id)

        if idx is None:
            dominant_topics = ["index_introuvable"]
        elif idx not in gamma_indexed.index:
            dominant_topics = ["absent_de_gamma"]
        else:
            row      = gamma_indexed.loc[idx]
            dominant = row[row >= GAMMA_THRESHOLD].sort_values(ascending=False)
            dominant_topics = (
                [str(t) for t in dominant.index.tolist()]
                if not dominant.empty
                else [str(row.idxmax())]
            )

        node_meta = nodes_df[nodes_df["Id"] == doc_id]
        title = node_meta["Label"].values[0]      if not node_meta.empty else ""
        year  = node_meta["year"].values[0]        if not node_meta.empty else ""
        thema = node_meta["label_thema"].values[0] if not node_meta.empty else ""

        rows.append({
            "doc_id"       : doc_id,
            "titre"        : title,
            "annee"        : year,
            "label_thema"  : thema,
            "topics_lda"   : ", ".join(dominant_topics),
            "nb_topics"    : len(dominant_topics),
            "corpus_index" : idx,
        })

    return pd.DataFrame(rows)


print("\n── Croisement corpus propre × composantes ────────────────────")

df_ccp = build_results(main_cc, "Composante connexe principale")

all_other_rows = []
for rank, cc in enumerate(other_ccs, start=2):
    df_cc = build_results(cc, f"Composante {rank} ({len(cc)} nœuds)")
    if not df_cc.empty:
        df_cc.insert(0, "composante_rang",   rank)
        df_cc.insert(1, "composante_taille", len(cc))
        all_other_rows.append(df_cc)

df_autres = (
    pd.concat(all_other_rows, ignore_index=True)
    if all_other_rows
    else pd.DataFrame()
)


ccp_path = OUTPUT_DIR / "publications_ccp_topics_lda.csv"
df_ccp.to_csv(ccp_path, index=False, encoding="utf-8-sig")
print(f"  → CCP       : {ccp_path.name}  ({len(df_ccp)} publications)")

autres_path = OUTPUT_DIR / "publications_autres_cc_topics_lda.csv"
if not df_autres.empty:
    df_autres.to_csv(autres_path, index=False, encoding="utf-8-sig")
    print(f"  → Autres CC : {autres_path.name}  ({len(df_autres)} publications "
          f"dans {len(other_ccs)} composantes)")
else:
    print("  → Autres CC : aucune publication du corpus propre dans les composantes secondaires.")



print(f"  Publications retenues dans la CCP        : {len(df_ccp)}")
print(f"  Publications retenues dans les autres CC : {len(df_autres)}")

if not df_ccp.empty:
    print("\n  Répartition par nb de topics (CCP) :")
    print(df_ccp["nb_topics"].value_counts().to_string())

if not df_autres.empty:
    print("\n  Répartition par nb de topics (autres CC) :")
    print(df_autres["nb_topics"].value_counts().to_string())
    print("\n  Publications par composante (rang) :")
    print(df_autres.groupby("composante_rang")["doc_id"].count().to_string())

print("\n  Aperçu CCP :")
print(df_ccp[["doc_id", "annee", "topics_lda", "titre"]].head(10).to_string(index=False))

if not df_autres.empty:
    print("\n  Aperçu autres CC :")
    print(df_autres[["composante_rang", "composante_taille", "doc_id",
                      "annee", "topics_lda", "titre"]].head(10).to_string(index=False))
