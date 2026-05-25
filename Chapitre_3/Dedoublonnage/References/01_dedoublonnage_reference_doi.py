"""
Dédoublonnage des références par champ DOI.

Pour chaque groupe de références partageant le même DOI normalisé :
  - Dry run  : affiche les groupes de doublons (title, year, doi) sans toucher la base.
  - Full run : conserve la référence la mieux renseignée (info_score), fusionne les
               champs de disponibilité, puis supprime les doublons.

Logique de conservation :
  - Même DOI + années proches (≤ 1 an d'écart) → doublons : on garde le mieux rempli.
  - Même DOI + années très éloignées (> 1 an)   → on conserve une référence par année
    (la mieux remplie) et on signale le conflit.
  - DOI absent ou 'nan'                          → conservé tel quel, jamais touché.
"""

import re
import mysql.connector
from mysql.connector import Error as MySQLError
from collections import defaultdict

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "PASSWORD",
    "database": "DATABASE",
}

# True  → aperçu seul, aucune écriture en base
# False → suppressions et fusions réelles
DRY_RUN = True

# Champs de disponibilité à fusionner par valeur maximale avant suppression
AVAILABILITY_FIELDS = ["disponibilite_persee", "dispo_JSTOR", "disponibilite_cairn"]


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

def normalize_doi(doi) -> str:
    """Retire préfixes URL, met en minuscule, supprime les espaces."""
    if doi is None:
        return ""
    doi = str(doi).strip().lower()
    doi = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:)", "", doi, flags=re.IGNORECASE)
    return doi


def info_score(row: dict) -> int:
    """Nombre de champs non-NULL et non-vides : sert de critère de conservation."""
    return sum(1 for v in row.values() if v is not None and str(v).strip() != "")


# ---------------------------------------------------------------------------
# Accès base de données
# ---------------------------------------------------------------------------

def fetch_references(cursor) -> list[dict]:
    cursor.execute(
        "SELECT id, title, year, doi, "
        "disponibilite_persee, dispo_JSTOR, disponibilite_cairn "
        "FROM reference"
    )
    return cursor.fetchall()


def group_by_doi(rows: list[dict]) -> dict[str, list[dict]]:
    """Regroupe les références par DOI normalisé ; exclut les DOI absents."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        doi = normalize_doi(row.get("doi"))
        if doi and doi != "nan":
            groups[doi].append(row)
    # Seuls les groupes avec au moins 2 entrées sont des doublons potentiels
    return {doi: refs for doi, refs in groups.items() if len(refs) > 1}


# ---------------------------------------------------------------------------
# Logique de décision
# ---------------------------------------------------------------------------

def resolve_group(refs: list[dict]) -> tuple[list[int], list[int], bool]:
    """
    Analyse un groupe de références partageant le même DOI.

    Retourne :
      - ids_to_keep    : liste d'IDs à conserver
      - ids_to_delete  : liste d'IDs à supprimer
      - year_conflict  : True si les années sont très éloignées (> 1 an)
    """
    # Associe chaque référence à son année numérique (None si absente)
    for r in refs:
        try:
            r["_year"] = int(r["year"]) if r.get("year") is not None else None
        except (ValueError, TypeError):
            r["_year"] = None

    years = sorted({r["_year"] for r in refs if r["_year"] is not None})
    year_conflict = len(years) >= 2 and (max(years) - min(years)) > 1

    if year_conflict:
        # Cas A — années très éloignées : une référence par année
        ids_to_keep, ids_to_delete = [], []
        by_year: dict = defaultdict(list)
        no_year = []
        for r in refs:
            if r["_year"] is not None:
                by_year[r["_year"]].append(r)
            else:
                no_year.append(r)

        for year_refs in by_year.values():
            scored = sorted(year_refs, key=info_score, reverse=True)
            ids_to_keep.append(scored[0]["id"])
            ids_to_delete.extend(r["id"] for r in scored[1:])

        # Références sans année : on garde la mieux renseignée
        if no_year:
            scored = sorted(no_year, key=info_score, reverse=True)
            ids_to_keep.append(scored[0]["id"])
            ids_to_delete.extend(r["id"] for r in scored[1:])

    else:
        # Cas B — années identiques ou proches : vrais doublons
        scored = sorted(refs, key=info_score, reverse=True)
        ids_to_keep = [scored[0]["id"]]
        ids_to_delete = [r["id"] for r in scored[1:]]

    return ids_to_keep, ids_to_delete, year_conflict


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------

def dry_run(groups: dict[str, list[dict]]) -> None:
    total_to_delete = 0

    print("=" * 70)
    print(f"DRY RUN — {len(groups)} groupe(s) de doublons détectés")
    print("=" * 70)

    for doi, refs in sorted(groups.items()):
        ids_to_keep, ids_to_delete, conflict = resolve_group(refs)
        total_to_delete += len(ids_to_delete)

        flag = "  ⚠ conflit d'années" if conflict else ""
        print(f"\nDOI : {doi}{flag}")
        print(f"  {'ID':<8}  {'Année':<6}  Titre")
        print(f"  {'-'*8}  {'-'*6}  {'-'*40}")

        for r in sorted(refs, key=lambda x: x.get("year") or 0):
            marker = "→ GARDER " if r["id"] in ids_to_keep else "  SUPPRIM."
            year   = r.get("year") or "—"
            title  = (str(r.get("title") or "").strip())[:60] or "(sans titre)"
            print(f"  {marker}  {r['id']:<6}  {str(year):<6}  {title}")

    print("\n" + "=" * 70)
    print(f"Total à supprimer : {total_to_delete} référence(s)")
    print("=" * 70)


# ---------------------------------------------------------------------------
# Full run
# ---------------------------------------------------------------------------

def full_run(cursor, groups: dict[str, list[dict]]) -> tuple[int, int]:
    kept = 0
    deleted = 0

    for refs in groups.values():
        ids_to_keep, ids_to_delete, _ = resolve_group(refs)

        # Fusion des champs de disponibilité sur la référence conservée
        # (on propage la valeur maximale rencontrée dans le groupe)
        for keep_id in ids_to_keep:
            group_for_keep = [r for r in refs if r["id"] == keep_id or r["id"] in ids_to_delete]
            for field in AVAILABILITY_FIELDS:
                max_val = max(
                    (r.get(field) or 0 for r in group_for_keep),
                    default=0,
                )
                cursor.execute(
                    f"UPDATE reference SET {field} = %s WHERE id = %s",
                    (max_val, keep_id),
                )

        # Suppression des doublons
        for del_id in ids_to_delete:
            cursor.execute("DELETE FROM reference WHERE id = %s", (del_id,))
            deleted += 1

        kept += len(ids_to_keep)

    return kept, deleted


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def main():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)

        rows = fetch_references(cursor)
        print(f"{len(rows)} références récupérées.")

        groups = group_by_doi(rows)
        print(f"{len(groups)} groupe(s) de doublons identifiés par DOI.\n")

        if DRY_RUN:
            dry_run(groups)
            print("\nDRY_RUN actif — aucune modification effectuée.")
        else:
            kept, deleted = full_run(cursor, groups)
            conn.commit()
            print(f"Terminé — {kept} conservée(s), {deleted} supprimée(s).")

        cursor.close()
        conn.close()

    except MySQLError as err:
        print(f"Erreur MySQL : {err}")
        if "conn" in dir():
            conn.rollback()


if __name__ == "__main__":
    main()