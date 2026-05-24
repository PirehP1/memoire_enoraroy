import mysql.connector
from typing import Optional
import re

DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'PASSWORD',
    'database': 'DATABASE'
}

REFERENCES_TABLE = 'reference'
TITLE_FIELD = 'title'
ID_FIELD = 'id'


def clean_title_string(title: Optional[str]) -> str:
    """Supprime les artefacts de début de titre : '.', ':', et crochets '[]'."""
    if not title:
        return ""
    cleaned_title = title.strip()

    # Supprime un point initial suivi d'un espace ou d'une lettre
    if cleaned_title.startswith('. '):
        cleaned_title = cleaned_title[2:].strip()
    elif cleaned_title.startswith('.') and len(cleaned_title) > 1 and cleaned_title[1].isalpha():
        cleaned_title = cleaned_title[1:].strip()

    # Supprime un deux-points initial
    if cleaned_title.startswith(':'):
        cleaned_title = cleaned_title[1:].strip()

    # Supprime les crochets initiaux, en retirant aussi le crochet fermant s'il existe
    if cleaned_title.startswith('['):
        cleaned_title = cleaned_title[1:].strip()
        try:
            closing_bracket_index = cleaned_title.index(']')
            cleaned_title = cleaned_title[:closing_bracket_index] + cleaned_title[closing_bracket_index+1:]
        except ValueError:
            pass

    return cleaned_title.strip()


def clean_titles_standalone():
    conn = None
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)

        cursor.execute(f"SELECT {ID_FIELD}, {TITLE_FIELD} FROM {REFERENCES_TABLE}")
        references = cursor.fetchall()

        updated_count = 0

        for ref in references:
            ref_id = ref[ID_FIELD]
            original_title = ref[TITLE_FIELD]
            new_title = clean_title_string(original_title)

            # Ne met à jour que si le titre a effectivement changé
            if new_title != original_title and new_title != "":
                cursor.execute(
                    f"UPDATE {REFERENCES_TABLE} SET {TITLE_FIELD} = %s, date_modified = NOW() WHERE {ID_FIELD} = %s",
                    (new_title, ref_id)
                )
                updated_count += 1

        conn.commit()
        print(f"{updated_count} titres mis à jour.")

    except mysql.connector.Error as err:
        print(f"Erreur MySQL : {err}")
        if conn and conn.is_connected():
            conn.rollback()

    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


if __name__ == "__main__":
    clean_titles_standalone()