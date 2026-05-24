import mysql.connector
import re
from typing import Optional
from html import unescape

DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'PASSWORD',
    'database': 'DATABASE'
}

TABLE_NAME = 'reference'
FIELDS_TO_CLEAN = ['title', 'secondary_title']
ID_FIELD = 'id'

# Regex ciblant uniquement les balises <span> et </span>
HTML_TAG_RE = re.compile(
    r'</?(?:b|i|sup|em|br|bold|span|xhtml:span)\b[^>]*>',
    flags=re.IGNORECASE
)

def clean_text(text: Optional[str]) -> Optional[str]:
    """Nettoie un champ texte : balises <span>, entités HTML, apostrophes doubles, espaces."""
    if not text:
        return text

    cleaned = text
    #décode les entités html
    cleaned = unescape(cleaned)
    # Supprime les balises <span ...> et </span>
    cleaned = HTML_TAG_RE.sub('', cleaned)
    # Remplace les apostrophes doubles '' par '
    cleaned = re.sub(r"''+", "'", cleaned)

    # Normalise les espaces multiples
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    return cleaned


def needs_cleaning(text: Optional[str]) -> bool:
    """Détecte la présence d'une balise <span> ou d'une entité HTML."""
    if not text:
        return False
    return bool(HTML_TAG_RE.search(text)) or '&' in text


def clean_database():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)

        fields_str = ', '.join([ID_FIELD] + FIELDS_TO_CLEAN)
        cursor.execute(f"SELECT {fields_str} FROM {TABLE_NAME}")
        rows = cursor.fetchall()

        cleaned_count = 0
        changes = []

        for row in rows:
            record_id = row[ID_FIELD]
            updates = {}

            for field in FIELDS_TO_CLEAN:
                original_value = row[field]

                if needs_cleaning(original_value):
                    cleaned_value = clean_text(original_value)

                    if cleaned_value != original_value:
                        updates[field] = cleaned_value
                        changes.append({
                            'id': record_id,
                            'field': field,
                            'original': original_value,
                            'cleaned': cleaned_value
                        })

            if updates:
                # Inclut date_modified dans la mise à jour
                set_clause = ', '.join([f"{field} = %s" for field in updates.keys()])
                set_clause += ', date_modified = NOW()'
                cursor.execute(
                    f"UPDATE {TABLE_NAME} SET {set_clause} WHERE {ID_FIELD} = %s",
                    list(updates.values()) + [record_id]
                )
                cleaned_count += 1

        conn.commit()
        print(f"{cleaned_count} enregistrements modifiés.")

        if changes:
            print("\nExemples de modifications (max 10) :")
            for change in changes[:10]:
                print(f"\nID {change['id']} - {change['field']}:")
                print(f"  Avant : {change['original'][:100]}")
                print(f"  Après : {change['cleaned'][:100]}")

        cursor.close()
        conn.close()

    except mysql.connector.Error as err:
        print(f"Erreur MySQL : {err}")
    except Exception as e:
        print(f"Erreur : {e}")


def preview_cleaning(limit: int = 50):
    """Prévisualise les modifications sans toucher à la base."""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)

        fields_str = ', '.join([ID_FIELD] + FIELDS_TO_CLEAN)
        cursor.execute(f"SELECT {fields_str} FROM {TABLE_NAME}")
        rows = cursor.fetchall()

        count = 0
        for row in rows:
            if count >= limit:
                break

            record_id = row[ID_FIELD]

            for field in FIELDS_TO_CLEAN:
                original_value = row[field]

                if needs_cleaning(original_value):
                    cleaned_value = clean_text(original_value)

                    if cleaned_value != original_value:
                        print(f"\nID {record_id} - {field}:")
                        print(f"  AVANT : {original_value}")
                        print(f"  APRÈS : {cleaned_value}")
                        print("-" * 80)
                        count += 1

                        if count >= limit:
                            break

        cursor.close()
        conn.close()

        if count == 0:
            print("Aucun nettoyage nécessaire.")

    except Exception as e:
        print(f"Erreur : {e}")


if __name__ == "__main__":
    choice = input("1. Prévisualiser  2. Nettoyer  3. Quitter\nChoix : ").strip()

    if choice == "1":
        preview_cleaning()
    elif choice == "2":
        confirm = input("Confirmer la modification de la base ? (oui/non) : ").strip().lower()
        if confirm == "oui":
            clean_database()
        else:
            print("Annulé.")