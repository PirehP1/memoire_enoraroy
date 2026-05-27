"""
step1_match_title_secondary.py
──────────────────────────────
Pour les références sans DOI, ISSN/ISBN ni année, filtre les paires
(ref MySQL, article JSTOR) dont les titres secondaires sont similaires.

Comparaison exhaustive : chaque article JSTOR est comparé contre toutes
les références. Pas de blocage — aucun match ne peut être manqué.

Produit candidate_pairs_titles.jsonl.
"""

import json
import os
import re
import unicodedata
from multiprocessing import Pool, cpu_count

import Levenshtein
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
OUTPUT_FILE  = "candidate_pairs_titles.jsonl"

# Seuil de pré-filtrage sur le titre secondaire (step 2 affinera)
MIN_SECONDARY_SIM = 0.75


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------
def normalize(t: str) -> str:
    if not t:
        return ""
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^\w\s]", " ", t)
    return " ".join(t.split())


def sim(a: str, b: str) -> float:
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return 0.0
    return Levenshtein.ratio(na, nb)


# ---------------------------------------------------------------------------
# Chargement des références depuis MySQL
# ---------------------------------------------------------------------------
def load_refs(config: dict) -> list:
    conn = mysql.connector.connect(**config)
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT id, title, secondary_title
        FROM `reference`
        WHERE (doi IS NULL OR doi = '')
          AND (issn IS NULL OR issn = '')
          AND (year IS NULL OR year = '')
          AND secondary_title IS NOT NULL AND secondary_title <> ''
    """)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    refs = [
        {
            "ref_id":             r["id"],
            "db_title":           r["title"]           or "",
            "db_secondary_title": r["secondary_title"] or "",
            "db_secondary_norm":  normalize(r["secondary_title"] or ""),
        }
        for r in rows
    ]
    print(f"{len(refs)} références chargées depuis MySQL")
    return refs


# ---------------------------------------------------------------------------
# Traitement d'un fichier JSTOR (parallèle)
# Reçoit la liste complète des refs normalisées.
# ---------------------------------------------------------------------------
def process_file(args: tuple) -> tuple[str, int, list]:
    filename, refs = args
    pairs = []
    articles_read = 0

    with open(os.path.join(JSTOR_FOLDER, filename), encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                article = json.loads(line)
            except json.JSONDecodeError:
                continue

            articles_read += 1
            js_secondary = article.get("is_part_of") or ""
            if not js_secondary:
                continue

            js_secondary_norm = normalize(js_secondary)

            for ref in refs:
                score = Levenshtein.ratio(ref["db_secondary_norm"], js_secondary_norm)
                if score >= MIN_SECONDARY_SIM:
                    pairs.append({
                        "ref_id":             ref["ref_id"],
                        "db_title":           ref["db_title"],
                        "db_secondary_title": ref["db_secondary_title"],
                        "secondary_sim":      round(score, 4),
                        "jstor_item_id":      article.get("item_id", ""),
                        "jstor_title":        article.get("title", ""),
                        "jstor_is_part_of":   js_secondary,
                        "jstor_url":          article.get("url", ""),
                    })

    return filename, articles_read, pairs


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("Chargement des références depuis MySQL…")
    refs = load_refs(DB_CONFIG)

    jsonl_files = sorted(f for f in os.listdir(JSTOR_FOLDER) if f.endswith(".jsonl"))
    total_files = len(jsonl_files)
    print(f"Traitement de {total_files} fichier(s) sur {max(1, cpu_count()-1)} cœur(s)…\n")

    all_pairs = []
    done = 0

    with Pool(processes=max(1, cpu_count() - 1)) as pool:
        for filename, articles_read, pairs in pool.imap_unordered(
            process_file, [(f, refs) for f in jsonl_files]
        ):
            done += 1
            all_pairs.extend(pairs)
            print(f"  [{done:02d}/{total_files}] {filename:<35} "
                  f"{articles_read:>7,} articles   {len(pairs):>4} paires   "
                  f"(cumul : {len(all_pairs)})")

    # Dédoublonnage et écriture
    seen    = set()
    written = 0
    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        for pair in all_pairs:
            key = (pair["ref_id"], pair["jstor_item_id"])
            if key not in seen:
                seen.add(key)
                out.write(json.dumps(pair, ensure_ascii=False) + "\n")
                written += 1

    print(f"\n{written} paires candidates → {OUTPUT_FILE}")


if __name__ == "__main__":
    main()