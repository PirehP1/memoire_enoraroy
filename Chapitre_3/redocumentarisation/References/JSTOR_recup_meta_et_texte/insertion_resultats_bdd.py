"""
05_insert_jstor_item_id.py
──────────────────────────
Lit les fichiers JSON de correspondances produits par les scripts de matching
et met à jour la colonne jstor_item_id dans la table `reference` MySQL.

Fichiers lus (dans l'ordre) :
  - resultats_doi_jstor.json
  - resultats_isbn_jstor.json
  - resultats_annee_jstor.json
  - resultats_titre_jstor.json

Règle : on n'écrase jamais un jstor_item_id déjà présent en base.
"""

import json
import os

import mysql.connector
from mysql.connector import Error as MySQLError

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DB_CONFIG = {
    "host":     "localhost",
    "user":     "root",
    "password": "SQL2025Enora",
    "database": "test_programme",
}

# Fichiers à lire, dans l'ordre de priorité (le premier trouvé pour une ref gagne)
INPUT_FILES = [
    "resultats_doi_jstor.json",
    "resultats_isbn_jstor.json",
    "resultats_annee_jstor.json",
    "resultats_titre_jstor.json",
]


# ---------------------------------------------------------------------------
# Lecture des fichiers de résultats
# ---------------------------------------------------------------------------
def load_matches(files: list) -> dict:
    """
    Retourne { ref_id: jstor_item_id } pour toutes les entrées trouvées.
    En cas de doublon entre fichiers, la première occurrence (ordre de la
    liste INPUT_FILES) est conservée.
    """
    matches = {}
    for filepath in files:
        if not os.path.exists(filepath):
            print(f"  {filepath} introuvable, ignoré")
            continue
        with open(filepath, encoding="utf-8") as fh:
            data = json.load(fh)
        new = 0
        for entry in data:
            if not entry.get("trouve"):
                continue
            item_id = entry.get("jstor_item_id")
            if not item_id:
                continue
            ref_id = entry["ref_id"]
            if ref_id not in matches:
                matches[ref_id] = item_id
                new += 1
        print(f"  ✓  {filepath:<40} {new:>5} nouveaux matches chargés")
    return matches


# ---------------------------------------------------------------------------
# Mise à jour MySQL
# ---------------------------------------------------------------------------
def update_db(config: dict, matches: dict):
    conn   = mysql.connector.connect(**config)
    cursor = conn.cursor()

    updated  = 0
    skipped  = 0   # ref_id déjà renseigné en base
    missing  = 0   # ref_id introuvable en base

    total = len(matches)
    for i, (ref_id, jstor_item_id) in enumerate(matches.items(), 1):
        if i % 500 == 0 or i == total:
            print(f"  {i:,}/{total:,} traités…", end="\r")

        cursor.execute(
            """
            UPDATE `reference`
            SET    jstor_item_id = %s
            WHERE  id = %s
              AND  (jstor_item_id IS NULL OR jstor_item_id = '')
            """,
            (jstor_item_id, ref_id),
        )
        if cursor.rowcount == 1:
            updated += 1
        else:
            # Vérifier si la ligne existe (rowcount 0 peut signifier déjà renseigné)
            cursor.execute("SELECT jstor_item_id FROM `reference` WHERE id = %s", (ref_id,))
            row = cursor.fetchone()
            if row is None:
                missing += 1
            else:
                skipped += 1

    conn.commit()
    cursor.close()
    conn.close()
    print()  # saut de ligne après \r
    return updated, skipped, missing


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("Lecture des fichiers de correspondances…")
    matches = load_matches(INPUT_FILES)
    print(f"\n{len(matches)} références avec un jstor_item_id à insérer\n")

    if not matches:
        print("Rien à faire.")
        return

    print("Mise à jour de la base MySQL…")
    updated, skipped, missing = update_db(DB_CONFIG, matches)

    print(f"\n{'─'*45}")
    print(f"  Mises à jour effectuées : {updated}")
    print(f"  Déjà renseignées (ignorées) : {skipped}")
    print(f"  Ref ID introuvables en base : {missing}")
    print(f"{'─'*45}")


if __name__ == "__main__":
    main()