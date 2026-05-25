"""
Applique les fusions d'auteurs décidées dans le fichier JSON n'importe quel script (changer la variable contenue dans le fichier)

Règles de lecture du JSON :
  - "action": "keep"   → auteur conservé
  - "action": "delete" → auteur supprimé après redirection de ses publications
  - "action": "skip"   → groupe entier ignoré (aucune modification)

Un groupe sans exactement un "keep" est ignoré avec un avertissement.

Opérations effectuées pour chaque auteur supprimé :
  1. Redirection dans la table `ecriture` : les lignes pointant vers l'auteur
     supprimé sont redirigées vers l'auteur conservé.
     Les doublons éventuels dans `ecriture` (même reference_id + même author_id)
     sont supprimés plutôt que mis à jour, pour éviter les violations de contrainte.
  2. Suppression de l'auteur dans la table `authors`.
"""

import json
import mysql.connector
from mysql.connector import Error as MySQLError

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "PASSWORD",
    "database": "DATABASE",
}

FICHIER_JSON = "doublons_auteurs_a_verifier.json" #ou n'importe lequel au final pour l'application des décisions

# True  → affiche ce qui serait fait, sans écrire en base
# False → applique les modifications réelles
DRY_RUN = True


# ---------------------------------------------------------------------------
# Lecture et validation du JSON
# ---------------------------------------------------------------------------

def load_groups(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_group(group: dict) -> tuple:
    """
    Vérifie la cohérence d'un groupe.

    Retourne :
      - keep_id    : ID à conserver (None si groupe invalide ou skip)
      - delete_ids : liste des IDs à supprimer
      - skip       : True si le groupe doit être ignoré
    """
    auteurs = group.get("auteurs", [])

    if any(a.get("action") == "skip" for a in auteurs):
        return None, [], True

    keeps   = [a["id"] for a in auteurs if a.get("action") == "keep"]
    deletes = [a["id"] for a in auteurs if a.get("action") == "delete"]

    if len(keeps) != 1:
        return None, [], True  # invalide : avertissement levé par l'appelant

    return keeps[0], deletes, False


# ---------------------------------------------------------------------------
# Fusion
# ---------------------------------------------------------------------------

def get_existing_reference_ids(cursor, author_id: int) -> set[int]:
    """Retourne l'ensemble des reference_id déjà associés à un auteur dans ecriture."""
    cursor.execute(
        "SELECT reference_id FROM ecriture WHERE author_id = %s",
        (author_id,),
    )
    return {row["reference_id"] for row in cursor.fetchall()}


def redirect_publications(cursor, keep_id: int, delete_id: int) -> dict:
    """
    Redirige les publications de delete_id vers keep_id dans la table ecriture.

    - Si la publication n'est pas encore associée à keep_id : mise à jour.
    - Si elle l'est déjà (doublon) : suppression de la ligne orpheline.

    Retourne un dict de compteurs pour le rapport.
    """
    existing_keep = get_existing_reference_ids(cursor, keep_id)

    cursor.execute(
        "SELECT id, reference_id FROM ecriture WHERE author_id = %s",
        (delete_id,),
    )
    rows = cursor.fetchall()

    updated = 0
    removed_duplicates = 0

    for row in rows:
        ecriture_id = row["id"]
        ref_id = row["reference_id"]

        if ref_id in existing_keep:
            # La publication est déjà liée à keep_id : on supprime le doublon
            cursor.execute(
                "DELETE FROM ecriture WHERE id = %s",
                (ecriture_id,),
            )
            removed_duplicates += 1
        else:
            # On redirige vers keep_id
            cursor.execute(
                "UPDATE ecriture SET author_id = %s WHERE id = %s",
                (keep_id, ecriture_id),
            )
            existing_keep.add(ref_id)
            updated += 1

    return {"updated": updated, "removed_duplicates": removed_duplicates}


def delete_author(cursor, author_id: int) -> None:
    cursor.execute("DELETE FROM authors WHERE id = %s", (author_id,))


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def main():
    groups = load_groups(FICHIER_JSON)
    print(f"{len(groups)} groupe(s) chargés depuis {FICHIER_JSON}.")
    if DRY_RUN:
        print("*** MODE DRY RUN — aucune modification en base ***\n")

    applied = skipped = warnings = 0
    total_deleted_authors = 0
    total_redirected = 0
    total_duplicate_links = 0

    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)

        for group in groups:
            nom = group.get("nom_normalise", "?")
            keep_id, delete_ids, skip = validate_group(group)

            if skip:
                skipped += 1
                continue

            if keep_id is None:
                keeps = [a["id"] for a in group["auteurs"] if a.get("action") == "keep"]
                print(
                    f"'{nom}' — ignoré : {len(keeps)} 'keep' trouvé(s) "
                    f"(attendu : 1)"
                )
                warnings += 1
                continue

            if not delete_ids:
                skipped += 1
                continue

            if DRY_RUN:
                for del_id in delete_ids:
                    pubs_del = next(
                        (
                            a["publications"]
                            for a in group["auteurs"]
                            if a["id"] == del_id
                        ),
                        [],
                    )
                    print(
                        f"'{nom}' — GARDER {keep_id} | "
                        f"SUPPRIMER {del_id} "
                        f"({len(pubs_del)} publication(s) à rediriger)"
                    )
            else:
                for del_id in delete_ids:
                    counters = redirect_publications(cursor, keep_id, del_id)
                    delete_author(cursor, del_id)

                    total_deleted_authors += 1
                    total_redirected += counters["updated"]
                    total_duplicate_links += counters["removed_duplicates"]

                    print(
                        f"'{nom}' — {keep_id} conservé | "
                        f"{del_id} supprimé "
                        f"({counters['updated']} lien(s) redirigé(s), "
                        f"{counters['removed_duplicates']} doublon(s) dans ecriture supprimé(s))"
                    )

            applied += 1

        if not DRY_RUN:
            conn.commit()
            print(f"\nCommit effectué.")
            print(
                f"Bilan : {total_deleted_authors} auteur(s) supprimé(s), "
                f"{total_redirected} lien(s) redirigé(s), "
                f"{total_duplicate_links} lien(s) en double supprimé(s)."
            )

        print(
            f"\n{'[DRY RUN] ' if DRY_RUN else ''}Terminé — "
            f"{applied} groupe(s) traité(s), "
            f"{skipped} ignoré(s), "
            f"{warnings} avertissement(s)."
        )

        cursor.close()
        conn.close()

    except MySQLError as err:
        print(f"Erreur MySQL : {err}")
        if "conn" in dir():
            conn.rollback()


if __name__ == "__main__":
    main()
