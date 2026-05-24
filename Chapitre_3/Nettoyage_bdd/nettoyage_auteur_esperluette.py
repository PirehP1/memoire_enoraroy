"""
Sépare les entrées auteurs dont le NomComplet contient une esperluette (&)
signalant plusieurs auteurs fusionnés en une seule ligne.
Pour chaque entrée : crée les auteurs individuels, transfère les liens
de la table `ecriture`, puis désactive l'entrée d'origine.
"""

import re
import mysql.connector
from mysql.connector import Error as MySQLError

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "PASSWORD",
    "database": "DATABASE",
}

# IDs des entrées à traiter (auteurs réels uniquement, conférences exclues)
TARGET_IDS = [29644, 29252, 29277, 29616, 13025, 9064, 29261, 8491]


def parse_name(full_name: str) -> tuple[str, str | None]:
    """Sépare 'Nom, Prénom' ou retourne le nom complet si pas de virgule."""
    full_name = full_name.strip().strip(",").strip("*").strip()
    if "," in full_name:
        nom, prenom = full_name.split(",", 1)
        return nom.strip(), prenom.strip().strip("*").strip() or None
    return full_name, None


def split_authors(nom_complet: str) -> list[str]:
    """
    Découpe la chaîne sur '&' (et '&amp;') en ignorant les parties vides.
    ex. : "Dupont, Jean & Martin, Paul" → ["Dupont, Jean", "Martin, Paul"]
    """
    raw = nom_complet.replace("&amp;", "&")
    parts = [p.strip().strip(",").strip() for p in raw.split("&")]
    return [p for p in parts if len(p) > 1]


def find_or_create_author(cursor, nom_complet: str) -> int:
    """Retourne l'id de l'auteur existant ou crée une nouvelle entrée."""
    cursor.execute("SELECT id FROM authors WHERE NomComplet = %s", (nom_complet,))
    row = cursor.fetchone()
    if row:
        return row["id"]
    nom, prenom = parse_name(nom_complet)
    cursor.execute(
        "INSERT INTO authors (NomComplet, Nom, Prenom, date_added, date_modified, ambigu) "
        "VALUES (%s, %s, %s, NOW(), NOW(), '0')",
        (nom_complet, nom, prenom),
    )
    return cursor.lastrowid


def transfer_links(cursor, old_id: int, new_ids: list[int]) -> int:
    """Duplique les liens ecriture de l'ancien auteur vers chaque nouvel auteur."""
    cursor.execute("SELECT reference_id FROM ecriture WHERE author_id = %s", (old_id,))
    ref_ids = [r["reference_id"] for r in cursor.fetchall()]
    count = 0
    for ref_id in ref_ids:
        for new_id in new_ids:
            cursor.execute(
                "SELECT 1 FROM ecriture WHERE reference_id = %s AND author_id = %s",
                (ref_id, new_id),
            )
            if not cursor.fetchone():
                cursor.execute(
                    "INSERT INTO ecriture (reference_id, author_id) VALUES (%s, %s)",
                    (ref_id, new_id),
                )
                count += 1
    return count


def main():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)

        fmt = ",".join(["%s"] * len(TARGET_IDS))
        cursor.execute(f"SELECT id, NomComplet FROM authors WHERE id IN ({fmt})", tuple(TARGET_IDS))
        rows = cursor.fetchall()

        for row in rows:
            old_id, nom_complet = row["id"], row["NomComplet"]
            parts = split_authors(nom_complet)

            if len(parts) < 2:
                print(f"ID {old_id} — ignoré (moins de 2 noms après découpage) : {nom_complet}")
                continue

            print(f"ID {old_id} : {nom_complet} → {parts}")
            new_ids = [find_or_create_author(cursor, p) for p in parts]
            n_links = transfer_links(cursor, old_id, new_ids)

            # Désactivation de l'entrée fusionnée
            cursor.execute(
                "UPDATE authors SET ambigu = '2', notes = CONCAT(IFNULL(notes,''), ' [séparé]') WHERE id = %s",
                (old_id,),
            )
            cursor.execute("DELETE FROM ecriture WHERE author_id = %s", (old_id,))
            print(f"  → {len(new_ids)} auteurs créés/trouvés, {n_links} lien(s) transféré(s).\n")

        conn.commit()
        print("Terminé.")
        cursor.close()
        conn.close()

    except MySQLError as err:
        print(f"Erreur MySQL : {err}")
        conn.rollback()


if __name__ == "__main__":
    main()