import mysql.connector
import re
import json
from typing import Optional

DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'PASSWORD',
    'database': 'DATABASE'
}

TABLE_NAME = 'reference'
FIELDS_TO_CHECK = ['title', 'secondary_title']
ID_FIELD = 'id'
OUTPUT_JSON = 'doi_extracted_from_titles.json'

# Préfixe optionnel : info:doi/, URL /doi/, doi:, ou "In:" sans mention doi
# Suivi du DOI : 10. + 4 chiffres min + / + suffixe
DOI_PATTERN = re.compile(
    r'(?:info:doi/|<?\s*https?://[^\s>]*/doi/|[-–,\s]*\bdoi\s*:\s*|In:\s+)?'
    r'(10\.\d{4,}/[\w\d._;():\-/]+)',
    flags=re.IGNORECASE
)

# Supprime aussi les URLs résiduelles contenant le DOI (ex: <https://...>)
URL_DOI_PATTERN = re.compile(
    r'<?\s*https?://[^\s>]*/doi/10\.\d{4,}/[\w\d._;():\-/>]+',
    flags=re.IGNORECASE
)


def extract_doi(text: Optional[str]) -> Optional[str]:
    """Retourne le premier DOI trouvé dans le texte, ou None."""
    if not text:
        return None
    match = DOI_PATTERN.search(text)
    return match.group(1) if match else None


def clean_doi_from_text(text: Optional[str]) -> Optional[str]:
    """Supprime le DOI, son préfixe et les URLs résiduelles, puis normalise les espaces."""
    if not text:
        return text
    cleaned = URL_DOI_PATTERN.sub('', text)
    cleaned = DOI_PATTERN.sub('', cleaned)
    # Supprime un tiret ou "In:" résiduel en fin de chaîne
    cleaned = re.sub(r'\s*[-–]+\s*$', '', cleaned).strip()
    cleaned = re.sub(r'\bIn:\s*$', '', cleaned).strip()
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def extract_and_clean():
    results = {}

    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)

        fields_str = ', '.join([ID_FIELD] + FIELDS_TO_CHECK)
        cursor.execute(f"SELECT {fields_str} FROM {TABLE_NAME}")
        rows = cursor.fetchall()

        updated_count = 0

        for row in rows:
            record_id = row[ID_FIELD]
            record_dois = {}
            updates = {}

            for field in FIELDS_TO_CHECK:
                original = row[field]
                doi = extract_doi(original)

                if doi:
                    record_dois[field] = doi
                    cleaned = clean_doi_from_text(original)

                    if cleaned != original:
                        updates[field] = cleaned

            if record_dois:
                results[record_id] = record_dois

            if updates:
                set_clause = ', '.join([f"{f} = %s" for f in updates.keys()])
                set_clause += ', date_modified = NOW()'
                cursor.execute(
                    f"UPDATE {TABLE_NAME} SET {set_clause} WHERE {ID_FIELD} = %s",
                    list(updates.values()) + [record_id]
                )
                updated_count += 1

        conn.commit()

        with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        print(f"{updated_count} enregistrements modifiés.")
        print(f"{len(results)} DOI extraits dans '{OUTPUT_JSON}'.")

        cursor.close()
        conn.close()

    except mysql.connector.Error as err:
        print(f"Erreur MySQL : {err}")
    except Exception as e:
        print(f"Erreur : {e}")


def preview():
    """Prévisualise les extractions sans modifier la base."""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)

        fields_str = ', '.join([ID_FIELD] + FIELDS_TO_CHECK)
        cursor.execute(f"SELECT {fields_str} FROM {TABLE_NAME}")
        rows = cursor.fetchall()

        count = 0
        for row in rows:
            record_id = row[ID_FIELD]
            for field in FIELDS_TO_CHECK:
                original = row[field]
                doi = extract_doi(original)
                if doi:
                    cleaned = clean_doi_from_text(original)
                    print(f"\nID {record_id} - {field}")
                    print(f"  DOI trouvé : {doi}")
                    print(f"  AVANT : {original[:120]}")
                    print(f"  APRÈS : {cleaned[:120]}")
                    print("-" * 80)
                    count += 1

        cursor.close()
        conn.close()

        if count == 0:
            print("Aucun DOI détecté.")

    except Exception as e:
        print(f"Erreur : {e}")


if __name__ == "__main__":
    choice = input("1. Prévisualiser  2. Extraire et nettoyer  3. Quitter\nChoix : ").strip()

    if choice == "1":
        preview()
    elif choice == "2":
        confirm = input("Confirmer la modification de la base ? (oui/non) : ").strip().lower()
        if confirm == "oui":
            extract_and_clean()
        else:
            print("Annulé.")