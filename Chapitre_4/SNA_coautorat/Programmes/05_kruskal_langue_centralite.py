import pandas as pd
from pathlib import Path
from scipy.stats import kruskal
from pymongo import MongoClient

BASE       = Path(__file__).resolve().parent.parent
PATH_FILE  = BASE / "output" / "pub_simple_nodes.csv"
OUTPUT_DIR = BASE / "output"
OUTPUT_CSV = OUTPUT_DIR / "kruskal_langue_centralite.csv"

MIN_GROUP  = 5

df = pd.read_csv(PATH_FILE, sep=None, engine="python", dtype=str)
df.columns = df.columns.str.strip().str.lower()

if "degree_w" in df.columns:
    df = df.rename(columns={"degree_w": "degree_weighted"})

print(f"Lignes initiales : {len(df)}")

df["id"] = df["id"].astype(str).str.strip()
if "pagerank" in df.columns:
    df["pagerank_num"] = pd.to_numeric(df["pagerank"], errors="coerce")
    df = df.sort_values("pagerank_num", ascending=False)

df = df.drop_duplicates(subset="id", keep="first").copy()
print(f"Publications uniques : {len(df)}")

client = MongoClient("mongodb://localhost:27017/")
db = client["references_biblio_mongo"]
collection = db["references"]

mongo_data = []
for doc in collection.find({}, {"_id": 1, "language_name": 1}):
    mongo_data.append({
        "id": str(doc["_id"]),
        "mongo_lang": doc.get("language_name")
    })
mongo_df = pd.DataFrame(mongo_data)

df = df.merge(mongo_df, on="id", how="left")
df["language"] = df["mongo_lang"]
df["language_name"] = df["mongo_lang"]

lang_col = "language" if "language" in df.columns else "language_name"
df["langue"] = df[lang_col].fillna("inconnu").astype(str).str.strip().str.lower()

exclude_langs = ["", "inconnu", "unknown"]
df = df[~df["langue"].isin(exclude_langs)]

print("\n" + "═"*40 + "\nPUBLICATIONS PAR LANGUE\n" + "═"*40)
print(df["langue"].value_counts())

metrics = [
    "degree", "degree_weighted", "closeness", "betweenness",
    "pagerank", "katz", "eigenvector", "clustering"
]

print("\n" + "═"*40 + "\nKRUSKAL-WALLIS : CENTRALITÉ vs LANGUE\n" + "═"*40)

# ← ajouté : liste pour collecter les résultats
results = []

for m in metrics:
    if m not in df.columns:
        continue

    df_metric = pd.DataFrame({
        "val": pd.to_numeric(df[m], errors="coerce"),
        "langue": df["langue"]
    }).dropna()

    groupes = [grp["val"].values for _, grp in df_metric.groupby("langue") if len(grp) >= MIN_GROUP]

    if len(groupes) < 2:
        print(f"{m:18} groupes insuffisants")
        results.append({"metrique": m, "H": None, "p_value": None, "n_groupes": len(groupes), "note": "groupes insuffisants"})  # ← ajouté
        continue

    H, p = kruskal(*groupes)
    print(f"{m:18} H = {H:10.4f}   p = {p:.4e}")
    results.append({"metrique": m, "H": round(H, 4), "p_value": f"{p:.4e}", "n_groupes": len(groupes), "note": ""})  # ← ajouté

# ← ajouté : export CSV
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
df_results = pd.DataFrame(results)
df_results.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
print(f"\n→ Résultats exportés : {OUTPUT_CSV}")

print("\nTerminé.")
