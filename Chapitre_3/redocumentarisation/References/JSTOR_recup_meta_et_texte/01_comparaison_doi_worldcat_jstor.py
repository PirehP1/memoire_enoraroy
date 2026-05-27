"""
match_doi_jstor.py
──────────────────
Croise les DOI de la base MySQL avec le champ `ithaka_doi` des fichiers
JSTOR (.jsonl) et produit resultats_doi_jstor.json.
"""

import json
import os
from multiprocessing import Pool, cpu_count

import mysql.connector
from mysql.connector import Error as MySQLError
from collections import defaultdict
from datetime import datetime

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DB_CONFIG = {
    "host":     "localhost",
    "user":     "root",
    "password": "PASSWORD",
    "database": "DATABASE",
}

JSTOR_FOLDER = "jstor_jsonl_filtre"
OUTPUT_FILE  = "resultats_doi_jstor.json"


# ---------------------------------------------------------------------------
# Chargement des DOI depuis MySQL
# ---------------------------------------------------------------------------
def load_dois_from_db(config):
    conn = mysql.connector.connect(**config)
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, doi FROM `reference` WHERE doi IS NOT NULL AND doi <> ''")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    # { doi: ref_id }
    return {row["doi"]: row["id"] for row in rows}


# ---------------------------------------------------------------------------
# Traitement d'un fichier JSTOR (parallèle)
# ---------------------------------------------------------------------------
def process_file(args):
    filename, known_dois = args
    matches = {}  # { doi: {item_id, url} }

    with open(os.path.join(JSTOR_FOLDER, filename), encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                article = json.loads(line)
            except json.JSONDecodeError:
                continue

            doi = article.get("ithaka_doi")
            if doi and doi in known_dois and doi not in matches:
                matches[doi] = {
                    "jstor_item_id": article.get("item_id"),
                    "jstor_url":     article.get("url"),
                }

    return matches


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("Chargement des DOI depuis MySQL…")
    doi_index = load_dois_from_db(DB_CONFIG)
    print(f"{len(doi_index)} DOI chargés")

    jsonl_files = [f for f in os.listdir(JSTOR_FOLDER) if f.endswith(".jsonl")]
    print(f"Traitement de {len(jsonl_files)} fichier(s) JSTOR…")

    known_dois = set(doi_index.keys())
    with Pool(processes=max(1, cpu_count() - 1)) as pool:
        results = pool.map(process_file, [(f, known_dois) for f in jsonl_files])

    # Fusion des résultats de chaque fichier
    global_matches = {}
    for matches in results:
        for doi, hit in matches.items():
            if doi not in global_matches:
                global_matches[doi] = hit

    # Construction de la sortie
    output = [
        {
            "ref_id":        doi_index[doi],
            "doi":           doi,
            "trouve":        doi in global_matches,
            "jstor_item_id": global_matches[doi]["jstor_item_id"] if doi in global_matches else None,
            "jstor_url":     global_matches[doi]["jstor_url"]     if doi in global_matches else None,
        }
        for doi in doi_index
    ]
    output.sort(key=lambda r: (not r["trouve"], r["ref_id"]))

    with open(OUTPUT_FILE, "w", encoding="utf-8") as fh:
        json.dump(output, fh, ensure_ascii=False, indent=2)

    found = sum(1 for r in output if r["trouve"])
    print(f"\nRésultats : {found}/{len(output)} trouvés ({100*found/len(output):.1f}%)")
    print(f"Fichier de sortie : {OUTPUT_FILE}")


if __name__ == "__main__":
    main()