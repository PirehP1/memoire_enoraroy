"""
Détecte les doublons de références par ISSN normalisé.

Pour chaque groupe de références partageant le même ISSN :
  - Affiche un résumé console.
  - Produit un fichier JSON listant les groupes à vérifier manuellement.

Structure du JSON de sortie :
  [
    {
      "issn": "12345678",
      "references": [
        { "id": 42, "title": "...", "secondary_title": "...", "year": 2001, "action": "keep" },
        { "id": 43, "title": "...", "secondary_title": "...", "year": 2001, "action": "delete" }
      ]
    },
    ...
  ]

Le champ "action" est pré-rempli avec une suggestion conservatrice :
  - "keep"   → référence ayant l'ID le plus petit (la plus ancienne en base)
  - "delete" → les autres

Modifiez librement les valeurs "action" dans le JSON avant de lancer
`appliquer_fusions_issn.py`.
Valeurs acceptées : "keep" | "delete" | "skip" (ignorer ce groupe entièrement).
"""

import json
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

FICHIER_SORTIE_JSON = "doublons_issn_a_verifier.json"


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

def normalize_issn(issn) -> str:
    """
    Conserve le premier ISSN si plusieurs sont présents (séparateur ; ou ,).
    Retire tirets, espaces et caractères parasites. Retourne une chaîne vide
    si le résultat fait moins de 7 caractères (ISSN invalide).
    """
    if issn is None:
        return ""
    first = re.split(r"[;,]", str(issn))[0].strip()
    cleaned = re.sub(r"[^0-9Xx]", "", first).upper()
    return cleaned if len(cleaned) >= 7 else ""


# ---------------------------------------------------------------------------
# Accès base de données
# ---------------------------------------------------------------------------

def fetch_references(cursor) -> list[dict]:
    cursor.execute(
        "SELECT id, title, secondary_title, year, issn "
        "FROM reference "
        "WHERE issn IS NOT NULL AND issn != ''"
    )
    return cursor.fetchall()


# ---------------------------------------------------------------------------
# Regroupement
# ---------------------------------------------------------------------------

def group_by_issn(rows: list[dict]) -> dict[str, list[dict]]:
    """Regroupe par ISSN normalisé ; ne conserve que les groupes avec ≥ 2 entrées."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        issn = normalize_issn(row.get("issn"))
        if issn:
            groups[issn].append(row)
    return {issn: refs for issn, refs in groups.items() if len(refs) > 1}


# ---------------------------------------------------------------------------
# Construction du JSON
# ---------------------------------------------------------------------------

def build_output(groups: dict[str, list[dict]]) -> list[dict]:
    """
    Construit la liste des groupes à exporter.
    Suggestion par défaut : on garde le plus petit ID (le plus ancien en base).
    """
    output = []
    for issn, refs in sorted(groups.items()):
        refs_sorted = sorted(refs, key=lambda r: r["id"])
        keep_id = refs_sorted[0]["id"]

        group = {
            "issn": issn,
            "references": [
                {
                    "id": r["id"],
                    "title": r.get("title") or "",
                    "secondary_title": r.get("secondary_title") or "",
                    "year": r.get("year"),
                    "action": "keep" if r["id"] == keep_id else "delete",
                }
                for r in refs_sorted
            ],
        }
        output.append(group)
    return output


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def main():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)

        rows = fetch_references(cursor)
        print(f"{len(rows)} références avec ISSN récupérées.")

        groups = group_by_issn(rows)
        print(f"{len(groups)} groupe(s) de doublons détectés par ISSN.")

        total_refs  = sum(len(v) for v in groups.values())
        total_sugg  = sum(len(v) - 1 for v in groups.values())
        print(f"{total_refs} référence(s) concernées, {total_sugg} suppression(s) suggérées.\n")

        output = build_output(groups)

        with open(FICHIER_SORTIE_JSON, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2, default=str)

        print(f"JSON exporté → {FICHIER_SORTIE_JSON}")
        print("Vérifiez et ajustez les champs 'action' (keep/delete/skip) avant fusion.")

        cursor.close()
        conn.close()

    except MySQLError as err:
        print(f"Erreur MySQL : {err}")


if __name__ == "__main__":
    main()