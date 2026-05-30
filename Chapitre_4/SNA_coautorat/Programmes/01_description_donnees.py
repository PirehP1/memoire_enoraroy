import json
import os
from pathlib import Path

import pandas as pd
from bson import ObjectId
from pymongo import MongoClient

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent

NODES_FILE = PROJECT_DIR / "Noeuds_et_aretes" / "nodes_all.csv"
EDGES_FILE = PROJECT_DIR / "Noeuds_et_aretes" / "edges_author_pub.csv"

MONGO_URI = "mongodb://localhost:27017"
MONGO_DB = "references_biblio_mongo"

OUTPUT_DIR = PROJECT_DIR / "output"
TEX_DIR = OUTPUT_DIR / "tex"
OUTPUT_PREFIX = str(OUTPUT_DIR / "result")

def load_csv(path, required):
    df = pd.read_csv(path, dtype=str)
    df.columns = df.columns.str.strip().str.lower()
    for col in required:
        if col not in df.columns:
            raise ValueError(f"Colonne manquante: {col}\nColonnes trouvées: {list(df.columns)}")
    return df


def extract_ids_from_nodes(nodes_path):
    print("Chargement du fichier de noeuds...")
    df = load_csv(nodes_path, required=["id", "type"])

    df_authors = df[df["type"] == "author"].copy()
    df_pubs = df[df["type"] == "publication"].copy()

    author_keys = df_authors["id"].dropna().tolist()
    pub_ids = df_pubs["id"].dropna().tolist()

    print(f"Auteurs trouvés : {len(author_keys):,}")
    print(f"Publications trouvées : {len(pub_ids):,}")

    return author_keys, pub_ids, df_authors


def connect_mongo(uri):
    print(f"Connexion à MongoDB ({uri})...")
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")

    db = client[MONGO_DB]
    col_refs = db["references"]
    col_authors = db["authors"]

    return col_refs, col_authors


def fetch_publications(col_refs, pub_ids):
    print(f"Récupération de {len(pub_ids):,} publications...")
    
    oids = []
    for pid in pub_ids:
        try:
            oids.append(ObjectId(pid))
        except Exception:
            pass

    BATCH = 1000
    rows = []
    for i in range(0, len(oids), BATCH):
        batch = oids[i : i + BATCH]
        docs = col_refs.find(
            {"_id": {"$in": batch}},
            {"language": 1, "language_name": 1, "year": 1}
        )
        for doc in docs:
            rows.append({
                "id": str(doc["_id"]),
                "language_name": doc.get("language_name") or doc.get("language"),
                "year": doc.get("year"),
            })
        print(f"\rRécupéré {min(i + BATCH, len(oids)):,} / {len(oids):,}", end="", flush=True)

    print()
    return pd.DataFrame(rows)


def fetch_authors(col_authors, author_keys, df_authors_csv):
    print(f"Récupération de {len(author_keys):,} auteurs...")
    
    BATCH = 1000
    rows = []
    for i in range(0, len(author_keys), BATCH):
        batch = author_keys[i : i + BATCH]
        docs = col_authors.find(
            {"cle": {"$in": batch}},
            {"cle": 1, "nationalites": 1, "identifiants": 1}
        )
        for doc in docs:
            nats = doc.get("nationalites")
            nb_nats = len(nats) if isinstance(nats, list) else 0
            identifiants = doc.get("identifiants")
            has_id = bool(identifiants and len(identifiants) > 0)

            rows.append({
                "cle": doc["cle"],
                "nb_nationalites": nb_nats,
                "has_identifiants": has_id,
            })
        print(f"\rRécupéré {min(i + BATCH, len(author_keys)):,} / {len(author_keys):,}", end="", flush=True)

    print()
    df = pd.DataFrame(rows)

    found_keys = set(df["cle"]) if not df.empty else set()
    missing = [k for k in author_keys if k not in found_keys]
    
    if missing:
        print(f"\nAttention : {len(missing):,} auteurs du CSV sont absents de MongoDB.")
        print("Détail des lignes complètes des auteurs manquants :")
        # On extrait et on affiche la ligne complète du CSV pour chaque auteur manquant
        df_missing_rows = df_authors_csv[df_authors_csv["id"].isin(missing)]
        for _, row in df_missing_rows.iterrows():
            print(f"  - {row.to_dict()}")
        print()

    return df, missing


def compute_stats(df_authors_csv, df_authors_mongo, df_pubs, missing_authors):
    print("Calcul des statistiques descriptives...")
    stats = {}

    # Auteurs
    total_auteurs = len(df_authors_csv)
    stats["total_auteurs"] = total_auteurs

    if "genre" in df_authors_csv.columns:
        genre_renseigne = df_authors_csv["genre"].notna() & (df_authors_csv["genre"].str.strip() != "") & (df_authors_csv["genre"].str.lower() != "unknown")
        nb_genre_ok = int(genre_renseigne.sum())
    else:
        nb_genre_ok = 0

    stats["genre_renseigne"] = nb_genre_ok
    stats["genre_non_renseigne"] = total_auteurs - nb_genre_ok

    if df_authors_mongo.empty:
        stats.update({"nationalites_aucune": "N/A", "nationalites_une": "N/A", "nationalites_plusieurs": "N/A", "sans_identifiant": "N/A"})
    else:
        n_missing = len(missing_authors)
        stats["nationalites_aucune"] = int((df_authors_mongo["nb_nationalites"] == 0).sum()) + n_missing
        stats["nationalites_une"] = int((df_authors_mongo["nb_nationalites"] == 1).sum())
        stats["nationalites_plusieurs"] = int((df_authors_mongo["nb_nationalites"] >= 2).sum())
        stats["sans_identifiant"] = int((~df_authors_mongo["has_identifiants"]).sum()) + n_missing

    # Publications
    total_pubs = len(df_pubs)
    stats["total_publications"] = total_pubs

    if df_pubs.empty:
        stats.update({"pubs_avec_langue": 0, "pubs_sans_langue": total_pubs})
    else:
        avec_langue = df_pubs["language_name"].notna() & (df_pubs["language_name"].str.strip() != "")
        nb_avec = int(avec_langue.sum())
        stats["pubs_avec_langue"] = nb_avec
        stats["pubs_sans_langue"] = total_pubs - nb_avec
        stats["langues_distinctes"] = int(df_pubs.loc[avec_langue, "language_name"].nunique())

        top_langues = df_pubs.loc[avec_langue, "language_name"].value_counts().head(10).reset_index()
        top_langues.columns = ["Langue", "Nb publications"]
        stats["top_langues"] = top_langues.to_dict(orient="records")

    return stats


def export_stats(stats, df_authors_mongo, df_pubs):
    print("Exportation des résultats...")
    
    # Export JSON
    stats_export = {k: v for k, v in stats.items() if k != "top_langues"}
    with open(f"{OUTPUT_PREFIX}_descriptive_stats.json", "w", encoding="utf-8") as f:
        json.dump(stats_export, f, indent=4, ensure_ascii=False)

    # Export CSV Résumé
    rows_summary = [
        ("Total auteurs", stats.get("total_auteurs", "N/A")),
        ("Genre renseigné", stats.get("genre_renseigne", "N/A")),
        ("Genre non renseigné", stats.get("genre_non_renseigne", "N/A")),
        ("Sans nationalité", stats.get("nationalites_aucune", "N/A")),
        ("Une nationalité", stats.get("nationalites_une", "N/A")),
        ("Plusieurs nationalités", stats.get("nationalites_plusieurs", "N/A")),
        ("Sans identifiant d'autorité", stats.get("sans_identifiant", "N/A")),
        ("Total publications", stats.get("total_publications", "N/A")),
        ("Publications avec langue", stats.get("pubs_avec_langue", "N/A")),
        ("Publications sans langue", stats.get("pubs_sans_langue", "N/A")),
        ("Langues distinctes", stats.get("langues_distinctes", "N/A")),
    ]
    df_summary = pd.DataFrame(rows_summary, columns=["Indicateur", "Valeur"])
    df_summary.to_csv(f"{OUTPUT_PREFIX}_descriptive_stats.csv", index=False)

    # Export LaTeX
    df_summary.to_latex(
        os.path.join(TEX_DIR, "descriptive_stats.tex"), index=False,
        caption="Statistiques descriptives du réseau de co-autorship",
        label="tab:descriptive_stats"
    )

    if stats.get("top_langues"):
        df_lang = pd.DataFrame(stats["top_langues"])
        df_lang.to_latex(
            os.path.join(TEX_DIR, "top_langues.tex"), index=False,
            caption="Distribution des 10 langues les plus représentées",
            label="tab:top_langues"
        )
        df_lang.to_csv(f"{OUTPUT_PREFIX}_top_langues.csv", index=False)

    # Exports enrichis
    if not df_authors_mongo.empty:
        df_authors_mongo.to_csv(f"{OUTPUT_PREFIX}_authors_enriched.csv", index=False)
    if not df_pubs.empty:
        df_pubs.to_csv(f"{OUTPUT_PREFIX}_publications_enriched.csv", index=False)
        
    print(f"Export terminé dans {OUTPUT_DIR}")


def main():
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        TEX_DIR.mkdir(parents=True, exist_ok=True)

        author_keys, pub_ids, df_authors_csv = extract_ids_from_nodes(NODES_FILE)
        col_refs, col_authors = connect_mongo(MONGO_URI)
        
        df_pubs = fetch_publications(col_refs, pub_ids)
        df_authors_mongo, missing_authors = fetch_authors(col_authors, author_keys, df_authors_csv)
        
        stats = compute_stats(df_authors_csv, df_authors_mongo, df_pubs, missing_authors)
        export_stats(stats, df_authors_mongo, df_pubs)

    except Exception as e:
        import traceback
        print(f"Erreur lors de l'exécution : {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main()
