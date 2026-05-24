import mysql.connector
import json
from typing import Optional

DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'PASSWORD',
    'database': 'DATABASE'
}

TABLE_NAME = 'reference'
ID_FIELD = 'id'
DOI_FIELD = 'doi'
INPUT_JSON = 'doi_extracted_from_titles.json'


def load_json() -> dict:
    try:
        with open(INPUT_JSON, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Fichier '{INPUT_JSON}' introuvable.")
        return {}
    except json.JSONDecodeError:
        print(f"Fichier '{INPUT_JSON}' invalide.")
        return {}


def insert_dois(data: dict):
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)

        updated_count = 0
        skipped_count = 0

        for record_id, fields in data.items():
            # Récupère le premier DOI trouvé, peu importe le champ source
            doi_to_insert = next(iter(fields.values()))

            # Vérifie l'état du champ doi actuel
            cursor.execute(
                f"SELECT {DOI_FIELD} FROM {TABLE_NAME} WHERE {ID_FIELD} = %s",
                (record_id,)
            )
            row = cursor.fetchone()

            if not row:
                skipped_count += 1
                continue

            current_doi = row[DOI_FIELD]

            # N'insère que si le champ est vide ou NULL
            if not current_doi or current_doi.strip() in ('', 'NA'):
                cursor.execute(
                    f"UPDATE {TABLE_NAME} SET {DOI_FIELD} = %s, date_modified = NOW() "
                    f"WHERE {ID_FIELD} = %s",
                    (doi_to_insert, record_id)
                )
                updated_count += 1
            else:
                skipped_count += 1

        conn.commit()
        print(f"{updated_count} DOI insérés.")
        print(f"{skipped_count} enregistrements ignorés (DOI déjà présent ou ID introuvable).")

        cursor.close()
        conn.close()

    except mysql.connector.Error as err:
        print(f"Erreur MySQL : {err}")
    except Exception as e:
        print(f"Erreur : {e}")


def preview(data: dict):
    """Prévisualise les insertions sans modifier la base."""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)

        count = 0
        for record_id, fields in data.items():
            doi_to_insert = next(iter(fields.values()))

            cursor.execute(
                f"SELECT {DOI_FIELD} FROM {TABLE_NAME} WHERE {ID_FIELD} = %s",
                (record_id,)
            )
            row = cursor.fetchone()

            if not row:
                continue

            current_doi = row[DOI_FIELD]

            if not current_doi or current_doi.strip() in ('', 'NA'):
                print(f"ID {record_id} : '{current_doi}' -> '{doi_to_insert}'")
                count += 1

        cursor.close()
        conn.close()

        if count == 0:
            print("Aucune insertion à effectuer.")
        else:
            print(f"\n{count} DOI seraient insérés.")

    except Exception as e:
        print(f"Erreur : {e}")


if __name__ == "__main__":
    data = load_json()
    if not data:
        exit()

    choice = input("1. Prévisualiser  2. Insérer  3. Quitter\nChoix : ").strip()

    if choice == "1":
        preview(data)
    elif choice == "2":
        confirm = input("Confirmer l'insertion dans la base ? (oui/non) : ").strip().lower()
        if confirm == "oui":
            insert_dois(data)
        else:
            print("Annulé.")