"""
step1_match_isbn_issn.py
────────────────────────
Croise les ISSN/ISBN de la base MySQL avec les fichiers JSTOR (.jsonl).
Produit candidate_pairs.jsonl : une ligne par paire (ref_db, article_jstor)
dont au moins un identifiant correspond.

Chaque ligne de sortie :
  {
    "ref_id":             <int>,
    "db_issn":            <str>,   # valeur brute en base
    "db_title":           <str>,
    "db_secondary_title": <str>,
    "identifier_matched": <str>,   # valeur normalisée ayant matché
    "jstor_item_id":      <str>,
    "jstor_title":        <str>,
    "jstor_is_part_of":   <str>,
    "jstor_url":          <str>
  }
"""

import json
import os
import re
from collections import defaultdict
from multiprocessing import Pool, cpu_count

import mysql.connector
from mysql.connector import Error as MySQLError

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
OUTPUT_FILE  = "candidate_pairs.jsonl"


# ---------------------------------------------------------------------------
# Normalisation ISBN / ISSN  (supprime tirets et espaces)
# ---------------------------------------------------------------------------
def normalize_id(s: str) -> str:
    if not s:
        return ""
    return re.sub(r"[\s\-]", "", str(s)).strip().lower()


# ---------------------------------------------------------------------------
# Chargement des références depuis MySQL
# ---------------------------------------------------------------------------
def load_refs_from_db(config: dict) -> dict:
    """
    Retourne { id_norm: [{'ref_id', 'db_issn', 'db_title', 'db_secondary_title'}] }
    Un enregistrement peut avoir plusieurs ISSN séparés par ';'.
    """
    conn = mysql.connector.connect(**config)
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT id, issn, title, secondary_title
        FROM   `reference`
        WHERE  issn IS NOT NULL AND issn <> ''
    """)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    index = defaultdict(list)
    for row in rows:
        # Le champ issn peut contenir plusieurs valeurs : "0084-3067; 2749-6228"
        for raw in re.split(r"[;,]", row["issn"]):
            norm = normalize_id(raw)
            if norm:
                index[norm].append({
                    "ref_id":             row["id"],
                    "db_issn":            row["issn"],
                    "db_title":           row["title"]           or "",
                    "db_secondary_title": row["secondary_title"] or "",
                })

    print(f"{len(rows)} références chargées → {len(index)} identifiants uniques")
    return dict(index)


# ---------------------------------------------------------------------------
# Traitement d'un fichier JSTOR (parallèle)
# ---------------------------------------------------------------------------
def process_file(args: tuple) -> list:
    filename, known_ids = args
    pairs = []

    with open(os.path.join(JSTOR_FOLDER, filename), encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                article = json.loads(line)
            except json.JSONDecodeError:
                continue

            ids_dict = article.get("identifiers") or {}
            jstor_ids = {
                normalize_id(ids_dict.get("print_issn")),
                normalize_id(ids_dict.get("online_issn")),
                normalize_id(ids_dict.get("print_isbn")),
                normalize_id(ids_dict.get("online_isbn")),
            }
            jstor_ids.discard("")

            for norm_id in jstor_ids:
                if norm_id in known_ids:
                    for ref in known_ids[norm_id]:
                        pairs.append({
                            **ref,
                            "identifier_matched": norm_id,
                            "jstor_item_id":      article.get("item_id", ""),
                            "jstor_title":        article.get("title", ""),
                            "jstor_is_part_of":   article.get("is_part_of", ""),
                            "jstor_url":          article.get("url", ""),
                        })

    return pairs


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("Chargement des identifiants depuis MySQL…")
    ref_index = load_refs_from_db(DB_CONFIG)

    jsonl_files = [f for f in os.listdir(JSTOR_FOLDER) if f.endswith(".jsonl")]
    print(f"Traitement de {len(jsonl_files)} fichier(s) JSTOR…")

    known_ids = set(ref_index.keys())
    with Pool(processes=max(1, cpu_count() - 1)) as pool:
        results = pool.map(process_file, [(f, ref_index) for f in jsonl_files])

    # Dédoublonnage : une même paire (ref_id, jstor_item_id) via deux identifiants
    seen   = set()
    total  = 0
    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        for pairs in results:
            for pair in pairs:
                key = (pair["ref_id"], pair["jstor_item_id"])
                if key not in seen:
                    seen.add(key)
                    out.write(json.dumps(pair, ensure_ascii=False) + "\n")
                    total += 1

    print(f"\n{total} paires candidates → {OUTPUT_FILE}")


if __name__ == "__main__":
    main()