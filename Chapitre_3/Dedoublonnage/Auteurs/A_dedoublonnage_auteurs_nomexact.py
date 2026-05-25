"""
Détecte les doublons d'auteurs par correspondance exacte du NomComplet normalisé.

La normalisation appliquée :
  - Mise en minuscules
  - Suppression des accents (décomposition Unicode NFD)
  - Suppression de tout ce qui n'est pas une lettre unicode ou un espace
  - Collapsage des espaces multiples

Pour chaque groupe d'auteurs partageant le même nom normalisé :
  - Récupère les publications liées (id + title) via la table `ecriture`
  - Produit un fichier JSON listant les groupes à vérifier manuellement

Structure du JSON de sortie :
  [
    {
      "nom_normalise": "dupont jean",
      "auteurs": [
        {
          "id": 1,
          "NomComplet": "Dupont, Jean",
          "publications": [
            {"id": 42, "title": "Article sur les Francs"},
            {"id": 87, "title": "Les Lombards au VIe siècle"}
          ],
          "action": "keep"
        },
        {
          "id": 2,
          "NomComplet": "Dupont Jean",
          "publications": [
            {"id": 42, "title": "Article sur les Francs"}
          ],
          "action": "delete"
        }
      ]
    },
    ...
  ]

Le champ "action" est pré-rempli avec une suggestion conservatrice :
  - "keep"   → auteur avec l'ID le plus petit (le plus ancien en base)
  - "delete" → les autres

Modifiez les valeurs "action" dans le JSON avant de lancer
`02_appliquer_doublons_auteurs.py`.
Valeurs acceptées : "keep" | "delete" | "skip" (ignorer ce groupe entièrement).
"""

import json
import re
import unicodedata
import mysql.connector
from mysql.connector import Error as MySQLError
from collections import defaultdict
from typing import Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "PASSWORD",
    "database": "DATABASE",
}

FICHIER_SORTIE_JSON = "doublons_auteurs_a_verifier.json"

# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

def normalize_name(name: Optional[str]) -> str:
    """
    Normalise un nom pour la comparaison :
      1. Mise en minuscules
      2. Décomposition NFD pour séparer les accents des lettres de base
      3. Suppression des marques diacritiques (catégorie Unicode 'Mn')
      4. Suppression de tout ce qui n'est pas une lettre unicode ou un espace
      5. Collapsage des espaces multiples
    """
    if not name:
        return ""
    s = str(name).lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^\w\s]", " ", s)
    return " ".join(s.split())


def fetch_authors_with_publications(cursor) -> dict[int, dict]:
    """
    Récupère tous les auteurs et leurs publications liées en une seule jointure.
    Retourne un dict {author_id: {"id": ..., "NomComplet": ..., "publications": [...]}}.
    """
    cursor.execute(
        """
        SELECT a.id, a.NomComplet, r.id AS ref_id, r.title
        FROM authors a
        LEFT JOIN ecriture e ON e.author_id = a.id
        LEFT JOIN reference r ON r.id = e.reference_id
        WHERE a.NomComplet IS NOT NULL AND a.NomComplet != ''
        ORDER BY a.id ASC, r.id ASC
        """
    )
    rows = cursor.fetchall()

    authors: dict[int, dict] = {}
    for row in rows:
        aid = row["id"]
        if aid not in authors:
            authors[aid] = {
                "id": aid,
                "NomComplet": row["NomComplet"],
                "publications": [],
            }
        if row["ref_id"] is not None:
            authors[aid]["publications"].append(
                {"id": row["ref_id"], "title": row["title"] or ""}
            )

    return authors


# ---------------------------------------------------------------------------
# Regroupement
# ---------------------------------------------------------------------------

def group_by_normalized_name(
    authors: dict[int, dict],
) -> dict[str, list[dict]]:
    """
    Regroupe les auteurs par nom normalisé.
    Ne conserve que les groupes contenant au moins 2 auteurs.
    """
    groups: dict[str, list[dict]] = defaultdict(list)
    for author in authors.values():
        key = normalize_name(author["NomComplet"])
        if key:
            groups[key].append(author)
    return {k: v for k, v in groups.items() if len(v) >= 2}


# ---------------------------------------------------------------------------
# Construction du JSON
# ---------------------------------------------------------------------------

def build_output(groups: dict[str, list[dict]]) -> list[dict]:
    """
    Construit la liste des groupes à exporter.
    Les publications sont déjà portées par chaque auteur (chargées en mémoire).
    Suggestion par défaut : on garde le plus petit ID (le plus ancien en base).
    """
    output = []
    total = len(groups)

    for idx, (nom_norm, auteurs) in enumerate(sorted(groups.items()), start=1):
        print(f"  [{idx}/{total}] '{nom_norm}' — {len(auteurs)} auteurs", end="\r")

        auteurs_tries = sorted(auteurs, key=lambda a: a["id"])
        keep_id = auteurs_tries[0]["id"]

        groupe = {
            "nom_normalise": nom_norm,
            "auteurs": [
                {
                    "id": auteur["id"],
                    "NomComplet": auteur["NomComplet"],
                    "publications": auteur["publications"],
                    "action": "keep" if auteur["id"] == keep_id else "delete",
                }
                for auteur in auteurs_tries
            ],
        }
        output.append(groupe)

    print()
    return output


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def main():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)

        print("Chargement des auteurs et de leurs publications...")
        authors = fetch_authors_with_publications(cursor)
        print(f"{len(authors)} auteurs chargés.")

        print("Regroupement par nom normalisé...")
        groups = group_by_normalized_name(authors)
        total_groups = len(groups)
        total_authors = sum(len(v) for v in groups.values())
        total_suggested = sum(len(v) - 1 for v in groups.values())
        print(
            f"{total_groups} groupe(s) de doublons détectés | "
            f"{total_authors} auteur(s) concernés | "
            f"{total_suggested} suppression(s) suggérée(s).\n"
        )

        output = build_output(groups)

        with open(FICHIER_SORTIE_JSON, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2, default=str)

        print(f"\nJSON exporté → {FICHIER_SORTIE_JSON}")
        print(
            "Vérifiez les champs 'action' (keep / delete / skip) "
            "avant de lancer appliquer_doublons_auteurs.py."
        )

        cursor.close()
        conn.close()

    except MySQLError as err:
        print(f"Erreur MySQL : {err}")


if __name__ == "__main__":
    main()