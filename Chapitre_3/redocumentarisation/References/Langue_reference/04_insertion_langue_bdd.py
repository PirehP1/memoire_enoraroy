"""
04_update_database.py
---------------------
Met à jour les champs `language` et `source_lang` de la table `reference`
à partir des résultats des scripts 01, 02 et 03.

Ordre de priorité : 01 (CrossRef) > 02 (DOI webpage) > 03 (spaCy titre)
Les entrées avec langue = 'none' ou non résolues sont ignorées.

Entrée  : resultats_01.json, resultats_02.json, resultats_03.json
Sortie  : mise à jour en base MySQL
"""

import json
import mysql.connector

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'PASSWORD',
    'database': 'DATABASE',
    'charset': 'utf8mb4',
}

# Fichiers dans l'ordre de priorité décroissante
INPUT_FILES = [
    'resultats_01.json',
    'resultats_02.json',
    'resultats_03.json',
]

# Normalisation des valeurs source_langue → valeur BDD
SOURCE_LABELS = {
    'crossref_api':       'crossref',
    'html_meta':          'doi_webpage',
    'spacy_page_content': 'doi_webpage',
    'spacy':              'spacy',
}

# ---------------------------------------------------------------------------
# Chargement et fusion des résultats
# ---------------------------------------------------------------------------

def load_results() -> dict[int, dict]:
    """
    Charge les trois fichiers JSON et fusionne les résultats.
    En cas de doublon, la source de priorité la plus haute (01 > 02 > 03) prime.
    Retourne un dict {id: {langue, source_langue}}.
    """
    merged = {}

    for path in INPUT_FILES:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                entries = json.load(f)
        except FileNotFoundError:
            print(f"  [!] Fichier non trouvé, ignoré : {path}")
            continue

        count = 0
        for entry in entries:
            ref_id = entry['id']
            langue = entry.get('langue') or entry.get('language')

            # Ignorer les entrées non résolues
            if not langue or langue == 'none':
                continue

            # Ne pas écraser une entrée déjà chargée (priorité au fichier 01)
            if ref_id not in merged:
                merged[ref_id] = {
                    'langue':        langue,
                    'source_langue': entry.get('source_langue') or entry.get('source'),
                }
                count += 1

        print(f"  {path} : {count} entrées chargées")

    return merged


# ---------------------------------------------------------------------------
# Mise à jour de la base
# ---------------------------------------------------------------------------

def update_database(results: dict[int, dict]) -> None:
    conn   = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()

    updated = 0
    skipped = 0

    for ref_id, data in results.items():
        source_raw   = data['source_langue'] or ''
        source_label = SOURCE_LABELS.get(source_raw, source_raw)

        cursor.execute(
            "UPDATE reference SET language = %s, source_lang = %s WHERE id = %s",
            (data['langue'], source_label, ref_id)
        )

        if cursor.rowcount:
            updated += 1
        else:
            skipped += 1

    conn.commit()
    cursor.close()
    conn.close()

    print(f"\n  Lignes mises à jour : {updated}")
    print(f"  Lignes ignorées (id inexistant) : {skipped}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("Chargement des résultats JSON...")
    results = load_results()
    print(f"  Total : {len(results)} références à mettre à jour\n")

    print("Mise à jour de la base de données...")
    update_database(results)

    print("\nTerminé.")


if __name__ == '__main__':
    main()