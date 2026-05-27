"""
step1_match_year.py
───────────────────
Filtre les paires (référence MySQL, article JSTOR) partageant la même année.
Produit candidate_pairs_year.jsonl.
"""

import json
import os
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
OUTPUT_FILE  = "candidate_pairs_year.jsonl"


# ---------------------------------------------------------------------------
# Chargement depuis MySQL
# Retourne { year: [{'ref_id', 'db_title', 'db_secondary_title', 'year'}, ...] }
# ---------------------------------------------------------------------------
def load_year_index(config: dict) -> dict:
    conn = mysql.connector.connect(**config)
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT id, title, secondary_title, year
        FROM `reference`
        WHERE year IS NOT NULL AND year <> ''
    """)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    index = defaultdict(list)
    for row in rows:
        year = str(row["year"]).strip()
        if year:
            index[year].append({
                "ref_id":             row["id"],
                "db_title":           row["title"]           or "",
                "db_secondary_title": row["secondary_title"] or "",
                "year":               year,
            })

    print(f"{len(rows)} références chargées → {len(index)} années distinctes")
    return dict(index)


# ---------------------------------------------------------------------------
# Traitement d'un fichier JSTOR (parallèle)
# ---------------------------------------------------------------------------
def process_file(args: tuple) -> list:
    filename, year_index = args
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

            jstor_title = article.get("title") or ""
            if not jstor_title:
                continue

            # Extraire l'année depuis published_date ("2012-01-0" → "2012")
            published = article.get("published_date") or ""
            year = published[:4] if published else ""
            if not year or year not in year_index:
                continue

            for ref in year_index[year]:
                pairs.append({
                    **ref,
                    "jstor_item_id":    article.get("item_id", ""),
                    "jstor_title":      jstor_title,
                    "jstor_is_part_of": article.get("is_part_of") or "",
                    "jstor_url":        article.get("url") or "",
                })

    return pairs


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("Chargement des références depuis MySQL…")
    year_index = load_year_index(DB_CONFIG)

    jsonl_files = [f for f in os.listdir(JSTOR_FOLDER) if f.endswith(".jsonl")]
    print(f"Traitement de {len(jsonl_files)} fichier(s) JSTOR…")

    with Pool(processes=max(1, cpu_count() - 1)) as pool:
        results = pool.map(process_file, [(f, year_index) for f in jsonl_files])

    seen  = set()
    total = 0
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