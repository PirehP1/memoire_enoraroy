import pandas as pd
import networkx as nx
import numpy as np
from pymongo import MongoClient
from scipy.stats import chi2_contingency, norm as sp_norm
from pathlib import Path

MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "references_biblio_mongo"
COLLECTION_NAME = "references"

BASE_DIR   = Path(__file__).resolve().parent.parent
EDGES_FILE = BASE_DIR / "Noeuds_et_aretes" / "edges_author_pub.csv"
NODES_FILE = BASE_DIR / "Noeuds_et_aretes" / "nodes_all.csv"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_CSV = OUTPUT_DIR / "khi2_topics_composante_principale.csv"

MIN_COUNT = 5  # effectif minimum pour inclure un topic


edges = pd.read_csv(EDGES_FILE)
nodes = pd.read_csv(NODES_FILE)

G = nx.from_pandas_edgelist(edges, source="Source", target="Target")
node_types = dict(zip(nodes["Id"].astype(str), nodes["Type"]))
nx.set_node_attributes(G, node_types, name="node_type")

largest_component = max(nx.connected_components(G), key=len)
publication_nodes = set(nodes.loc[nodes["Type"] == "publication", "Id"].astype(str))

main_publications  = largest_component & publication_nodes
other_publications = publication_nodes - main_publications

# ============================================================
# RÉCUPÉRATION DES TOPICS (MONGODB)
# ============================================================
client = MongoClient(MONGO_URI)
collection = client[DB_NAME][COLLECTION_NAME]

topic_counts = {}
cursor = collection.find({}, {"_id": 1, "topic_analysis.topic_id": 1, "topic_analysis.label": 1})

for doc in cursor:
    doc_id = str(doc["_id"])
    topic_data = doc.get("topic_analysis") or {}
    
    t_id = topic_data.get("topic_id", "NO_TOPIC")
    t_label = topic_data.get("label", "Sans topic")
    topic_name = f"{t_id} | {t_label}"

    if topic_name not in topic_counts:
        topic_counts[topic_name] = {"main": 0, "other": 0}

    if doc_id in main_publications:
        topic_counts[topic_name]["main"] += 1
    elif doc_id in other_publications:
        topic_counts[topic_name]["other"] += 1

# ============================================================
# STATISTIQUES (KHI²)
# ============================================================
# Filtrage et tri des topics
filtered_counts = {t: c for t, c in topic_counts.items() if (c["main"] + c["other"]) >= MIN_COUNT}
topics_list = sorted(filtered_counts.keys())

O = np.array([[filtered_counts[t]["main"], filtered_counts[t]["other"]] for t in topics_list], dtype=float)

# Test du Chi2 global
chi2_global, p_global, dof_global, E = chi2_contingency(O)

print("═"*60)
print(f"Chi2 global : {chi2_global:.4f}  |  ddl : {dof_global}  |  p : {p_global:.6e}")
print(f"Effectif total : {int(O.sum())}")
print("═"*60)

# Calcul des résidus ajustés et des contributions
N = O.sum()
marg_row = O.sum(axis=1, keepdims=True) / N
marg_col = O.sum(axis=0, keepdims=True) / N

residus_adj = (O - E) / np.sqrt(E * (1 - marg_row) * (1 - marg_col))
contributions = ((O - E) ** 2 / E) / chi2_global * 100

rows = []
for i, t in enumerate(topics_list):
    r_adj = residus_adj[i, 0]
    p_val = 2 * (1 - sp_norm.cdf(abs(r_adj)))
    
    # Détermination textuelle de la représentation
    if abs(r_adj) < 1.96:
        representation = "ns"
    else:
        representation = "SUR (+)" if r_adj > 0 else "SOUS (-)"

    rows.append({
        "Topic": t,
        "Obs (Main)": int(O[i, 0]),
        "Att (Main)": round(E[i, 0], 1),
        "Residu Ajusté": round(r_adj, 2),
        "p-value": f"{p_val:.4e}",
        "Statut": representation,
        "Contrib Tot (%)": round(contributions[i, 0] + contributions[i, 1], 2)
    })

# Création du DataFrame final trié par le niveau de sur-représentation
df_resultats = pd.DataFrame(rows).sort_values("Residu Ajusté", ascending=False)

# Sauvegarde CSV
df_resultats.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
print(f"\nCSV exporté : {OUTPUT_CSV}\n")

print(df_resultats.to_string(index=False))
