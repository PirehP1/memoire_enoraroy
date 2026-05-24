"""
Décode les entités HTML résiduelles dans les champs NomComplet, Nom et Prenom
pour une liste d'IDs ciblés.
Gère les entités nommées (&aring;, &ouml;...), numériques (&#x11f;, &#237;...)
et les cas tronqués (entité sans point-virgule final).
"""

import re
import html
import unicodedata
import mysql.connector
from mysql.connector import Error as MySQLError

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "PASSWORD",
    "database": "DATABASE",
}

# IDs à corriger
TARGET_IDS = [18344, 28311, 19083, 18797, 46022, 25211, 26593, 19463, 18921]


def fix_entities(text: str) -> str:
    """
    Décode les entités HTML et normalise le résultat en Unicode NFC.
    Ajoute un point-virgule aux entités numériques tronquées avant décodage.
    ex. : "&#237" → "&#237;" → "í"
    """
    if not text:
        return text
    # Compléter les entités numériques sans point-virgule final
    text = re.sub(r"(&#x?[0-9a-fA-F]+)(?!;)", r"\1;", text)
    # Décoder toutes les entités HTML
    decoded = html.unescape(text)
    # Composer les caractères combinés (ex. o + ◌́ → ó)
    return unicodedata.normalize("NFC", decoded)


def main():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)

        fmt = ",".join(["%s"] * len(TARGET_IDS))
        cursor.execute(
            f"SELECT id, NomComplet, Nom, Prenom FROM authors WHERE id IN ({fmt})",
            tuple(TARGET_IDS),
        )
        rows = cursor.fetchall()

        for row in rows:
            new_nom_complet = fix_entities(row["NomComplet"])
            new_nom         = fix_entities(row["Nom"])
            new_prenom      = fix_entities(row["Prenom"])

            print(f"ID {row['id']}:")
            print(f"  Avant : {row['NomComplet']}")
            print(f"  Après : {new_nom_complet}\n")

            cursor.execute(
                "UPDATE authors SET NomComplet = %s, Nom = %s, Prenom = %s WHERE id = %s",
                (new_nom_complet, new_nom, new_prenom, row["id"]),
            )

        conn.commit()
        print(f"✓ {len(rows)} enregistrement(s) mis à jour.")
        cursor.close()
        conn.close()

    except MySQLError as err:
        print(f"Erreur MySQL : {err}")
        conn.rollback()


if __name__ == "__main__":
    main()