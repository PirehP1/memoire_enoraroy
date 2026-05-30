import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from pymongo import MongoClient
from pathlib import Path

# =============================================================================
# PARAMÈTRE PRINCIPAL — modifier ici pour changer la métrique visualisée
# Valeurs possibles : "betweenness", "degree", "eigenvector", "pagerank",
#                     "katz", "clustering", "degree_w"
# =============================================================================
METRIC = "betweenness"

# NOTE MÉTHODOLOGIQUE : les auteurs ayant plusieurs nationalités sont dupliqués
# (une ligne par pays après la jointure MongoDB). Chaque nationalité reçoit donc
# le même score que l'auteur concerné. Cela gonfle légèrement les effectifs des
# pays les plus représentés mais permet une lecture par nationalité plutôt que
# par auteur. Ce choix est signalé dans le titre du graphe.
# Aussi, compte tenu de la faible part d'auteurs multinationaux,...


BASE        = Path(__file__).resolve().parent.parent
OUTPUT_DIR  = BASE / "output"

OUTPUT_PATH = OUTPUT_DIR / f"boxplot_{METRIC}_nationalite.png"

aut = pd.read_csv(OUTPUT_DIR / "auteur_simple_nodes.csv")



# Vérification que la métrique demandée existe bien dans le fichier
if METRIC not in aut.columns:
    raise ValueError(
        f"La métrique '{METRIC}' est absente du fichier CSV.\n"
        f"Colonnes disponibles : {list(aut.columns)}"
    )

# 2. Connexion à MongoDB et extraction des nationalités
client = MongoClient("mongodb://localhost:27017/")
db = client["references_biblio_mongo"]
collection = db["authors"]

mongo_data = []
for doc in collection.find({}, {"cle": 1, "nationalites.nom_pays": 1, "_id": 0}):
    author_id = doc.get("cle")
    if not author_id:
        continue
    
    nationalites = doc.get("nationalites")
    if isinstance(nationalites, list) and len(nationalites) > 0:
        for nat in nationalites:
            nom_pays = nat.get("nom_pays")
            mongo_data.append({
                "id": author_id,
                "nationalite": nom_pays.strip() if nom_pays else "Inconnu"
            })
    else:
        mongo_data.append({
            "id": author_id,
            "nationalite": "Inconnu"
        })

enr_df = pd.DataFrame(mongo_data)

# 3. Fusion et préparation des données
df = aut.merge(enr_df, on="id", how="left")
df["nationalite"] = df["nationalite"].fillna("Inconnu").replace("", "Inconnu")
df[METRIC] = pd.to_numeric(df[METRIC], errors="coerce")  # ← dynamique

# Top 8 nationalités hors Inconnu
top = [n for n in df["nationalite"].value_counts().head(9).index if n != "Inconnu"][:8]

# Effectifs avant et après filtre des 0
effectifs_avant = df[df["nationalite"].isin(top)].groupby("nationalite").size()
df_nonzero      = df[df["nationalite"].isin(top) & df[METRIC].gt(0)].copy()  # ← dynamique
effectifs_apres = df_nonzero.groupby("nationalite").size()

# Groupes triés par médiane
groupes = [
    (nat, df_nonzero[df_nonzero["nationalite"] == nat][METRIC].dropna().values)  # ← dynamique
    for nat in top
]
groupes.sort(key=lambda x: np.median(x[1]))

# Labels avec effectifs
labels = [
    f"{nat}  (n={effectifs_apres.get(nat, 0):,} / {effectifs_avant.get(nat, 0):,})"
    for nat, _ in groupes
]

fig, ax = plt.subplots(figsize=(12, 6))
ax.boxplot(
    [g[1] for g in groupes],
    labels=labels,
    vert=False,
    patch_artist=True,
    showfliers=True,
    flierprops=dict(marker="o", markersize=2, alpha=0.3),
    boxprops=dict(facecolor="#cce5ff"),
    medianprops=dict(color="red", linewidth=2),
)

# Moyennes
for i, (nat, vals) in enumerate(groupes, start=1):
    ax.scatter(np.mean(vals), i, marker="D", color="orange", s=40, zorder=5,
               label="Moyenne" if i == 1 else "")

ax.set_xscale("log")
ax.set_xlabel(f"{METRIC.capitalize()} (échelle log)")  # ← dynamique
ax.set_title(
    f"Distribution de la {METRIC} par nationalité (LCC)\n"
    "Auteurs multinationaux comptés une fois par pays — "
    f"n retenu ({METRIC} > 0) / n total — médiane en rouge, moyenne en orange"  # ← dynamique + note méthodologique
)
ax.legend(loc="lower right")
ax.grid(axis="x", alpha=0.3, linestyle=":")
ax.spines[["top", "right"]].set_visible(False)
plt.tight_layout()
plt.savefig(OUTPUT_PATH, dpi=200, bbox_inches="tight")
print(f"→ Graphique sauvegardé : {OUTPUT_PATH}")
