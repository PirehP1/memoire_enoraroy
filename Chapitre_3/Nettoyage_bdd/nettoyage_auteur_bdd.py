"""
Nettoyage du champ NomComplet dans la table `authors`.
  - Supprime les parenthèses englobantes  : "(Dupont, Jean)" = "Dupont, Jean"
  - Supprime les astérisques              : "Dupont*, Jean"  = "Dupont, Jean"
  - Extrait les ORCID concaténés au nom   : "Dupont; https://orcid.org/..." = colonne dédiée
"""

import re
from typing import Optional
import mysql.connector
from mysql.connector import Error as MySQLError

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "PASSWORD",
    "database": "DATABASE",
}

# Regex : parenthèses englobantes, astérisques, séparateur ORCID
FULL_PARENS_RE = re.compile(r"^\s*\((.*)\)\s*$")
STARS_RE       = re.compile(r"\*+")
ORCID_SEP_RE   = re.compile(r";\s*https://orcid\.org/")


def needs_cleaning(text: Optional[str]) -> bool:
    """Renvoie True si le champ contient au moins une anomalie à corriger."""
    if not text:
        return False
    return bool(FULL_PARENS_RE.match(text) or STARS_RE.search(text) or ORCID_SEP_RE.search(text))


def clean_author_name(text: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Nettoie le nom et extrait l'ORCID. Retourne (nom_nettoyé, orcid_ou_None)."""
    if not text:
        return text, None

    # 1. Suppression des parenthèses englobantes
    match = FULL_PARENS_RE.match(text)
    cleaned = match.group(1).strip() if match else text

    # 2. Suppression des astérisques
    cleaned = STARS_RE.sub("", cleaned)

    # 3. Séparation nom / ORCID
    orcid = None
    if "; https://orcid.org/" in cleaned:
        nom_part, orcid_part = cleaned.split("; https://orcid.org/", maxsplit=1)
        cleaned = nom_part.strip()
        orcid   = f"https://orcid.org/{orcid_part.strip()}"

    return cleaned, orcid


def get_connection():
    return mysql.connector.connect(**DB_CONFIG)


def ensure_orcid_column(cursor):
    """Crée la colonne `orcid` si elle n'existe pas encore."""
    cursor.execute("SHOW COLUMNS FROM authors LIKE 'orcid'")
    if cursor.fetchone() is None:
        cursor.execute("ALTER TABLE authors ADD COLUMN orcid VARCHAR(255)")
        print("Colonne 'orcid' créée.\n")


def preview(limit: int = 50) -> None:
    """Affiche les modifications prévues sans toucher à la base."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, NomComplet FROM authors")

    count = 0
    for row in cursor.fetchall():
        if count >= limit:
            break
        if not needs_cleaning(row["NomComplet"]):
            continue
        cleaned, orcid = clean_author_name(row["NomComplet"])
        if cleaned == row["NomComplet"] and orcid is None:
            continue
        print(f"ID {row['id']}:")
        print(f"  Avant : {row['NomComplet']}")
        print(f"  Après : {cleaned}" + (f"\n  ORCID : {orcid}" if orcid else ""))
        print("-" * 60)
        count += 1

    if count == 0:
        print("Aucun nettoyage nécessaire.")
    cursor.close()
    conn.close()


def clean_database() -> int:
    """Applique le nettoyage sur toute la table. Retourne le nombre de lignes modifiées."""
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        ensure_orcid_column(cursor)

        cursor.execute("SELECT id, NomComplet FROM authors")
        rows = cursor.fetchall()
        print(f"Analyse de {len(rows)} enregistrements...\n")

        count = 0
        for row in rows:
            if not needs_cleaning(row["NomComplet"]):
                continue
            cleaned, orcid = clean_author_name(row["NomComplet"])
            if cleaned == row["NomComplet"] and orcid is None:
                continue

            cursor.execute(
                "UPDATE authors SET NomComplet = %s, orcid = %s WHERE id = %s",
                (cleaned, orcid, row["id"]),
            )
            count += 1

        conn.commit()
        print(f"✓ {count} enregistrement(s) modifié(s).")
        cursor.close()
        conn.close()
        return count

    except MySQLError as err:
        print(f"Erreur MySQL : {err}")
        return 0


if __name__ == "__main__":
    print("1. Prévisualiser\n2. Appliquer\n3. Quitter")
    choice = input("Choix : ").strip()

    if choice == "1":
        preview()
    elif choice == "2":
        if input("Confirmer la modification de la base ? (oui/non) : ").strip().lower() == "oui":
            clean_database()
        else:
            print("Annulé.")