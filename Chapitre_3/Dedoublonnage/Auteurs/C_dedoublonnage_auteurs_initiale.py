"""
Détecte les doublons d'auteurs par similarité du NomComplet
et par correspondance d'initiales de prénom.

Logique de détection (deux critères, appliqués au sein du même bloc) :
  (a) Ratio Levenshtein entre NomComplet normalisés >= SEUIL_SIMILARITE
  (b) Noms de famille identiques ET le prénom de l'un est une initiale
      (préfixe de moins de 3 caractères) du prénom de l'autre.
      Ex. : "Dupont J." vs "Dupont Jean".

Stratégie de blocage : groupement par nom de famille normalisé (`Nom`)
pour réduire le nombre de comparaisons à celles qui sont plausibles.

Union-Find : garantit la transitivité des paires détectées
(A ~ B et B ~ C → même cluster).

Sortie JSON :
  [
    {
      "nom_normalise": "dupont jean",
      "auteurs": [
        { "id": 1, "NomComplet": "Dupont, Jean",
          "publications": [{"id": 42, "title": "..."}],
          "action": "keep" },
        { "id": 7, "NomComplet": "Dupont J.",
          "publications": [...],
          "action": "delete" }
      ]
    }, ...
  ]

Suggestion par défaut : "keep" pour le plus petit ID (le plus ancien en base),
"delete" pour les autres. Modifiez les valeurs "action" avant d'appliquer.
Valeurs acceptées : "keep" | "delete" | "skip" (ignorer tout le groupe).
"""

import json
import re
import unicodedata
import mysql.connector
from mysql.connector import Error as MySQLError
from collections import defaultdict
from typing import Optional
import Levenshtein

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "PASSWORD",
    "database": "DATABASE",
}
FICHIER_SORTIE_JSON = "doublons_auteurs_initiales.json"
SEUIL_SIMILARITE = 0.85  # Ratio Levenshtein sur les NomComplet normalisés


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------
def normalize_name(name: Optional[str]) -> str:
    """
    Normalise un nom pour la comparaison :
      1. Mise en minuscules.
      2. Décomposition NFD pour isoler les diacritiques des lettres de base.
      3. Suppression des marques diacritiques (catégorie Unicode 'Mn').
      4. Suppression de tout caractère non alphabétique unicode ou non-espace.
         (\w est unicode-aware par défaut en Python 3)
      5. Collapsage des espaces multiples.
    """
    if not name:
        return ""
    s = str(name).lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^\w\s]", " ", s)
    return " ".join(s.split())


# ---------------------------------------------------------------------------
# Critère (b) : correspondance d'initiales
# ---------------------------------------------------------------------------
def is_initial_match(prenom1: Optional[str], prenom2: Optional[str]) -> bool:
    """
    Retourne True si l'un des deux prénoms normalisés est une initiale
    (préfixe de moins de 3 caractères) de l'autre.
    Ex. : "j" est une initiale de "jean" → True.
    """
    p1 = normalize_name(prenom1)
    p2 = normalize_name(prenom2)
    if not p1 or not p2:
        return False
    if len(p1) < 3 and p2.startswith(p1):
        return True
    if len(p2) < 3 and p1.startswith(p2):
        return True
    return False


# ---------------------------------------------------------------------------
# Union-Find — transitivité des paires
# ---------------------------------------------------------------------------
class UnionFind:
    """Structure Union-Find à compression de chemin."""

    def __init__(self):
        self._p: dict[int, int] = {}

    def find(self, x: int) -> int:
        self._p.setdefault(x, x)
        if self._p[x] != x:
            self._p[x] = self.find(self._p[x])
        return self._p[x]

    def union(self, x: int, y: int) -> None:
        rx, ry = self.find(x), self.find(y)
        if rx != ry:
            self._p[max(rx, ry)] = min(rx, ry)

    def clusters(self, ids: list[int]) -> list[list[int]]:
        """Retourne les groupes d'au moins 2 éléments."""
        groups: dict[int, list[int]] = defaultdict(list)
        for i in ids:
            groups[self.find(i)].append(i)
        return [v for v in groups.values() if len(v) >= 2]


# ---------------------------------------------------------------------------
# Chargement unique : auteurs + publications en une seule requête
# ---------------------------------------------------------------------------
def fetch_authors_with_publications(cursor) -> dict[int, dict]:
    """
    Récupère tous les auteurs et leurs publications liées en une seule jointure.
    Retourne un dict {author_id: {"id": ..., "NomComplet": ..., "Nom": ...,
    "Prenom": ..., "publications": [...]}}.
    """
    cursor.execute(
        """
        SELECT a.id, a.NomComplet, a.Nom, a.Prenom, r.id AS ref_id, r.title
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
                "Nom": row["Nom"],
                "Prenom": row["Prenom"],
                "publications": [],
            }
        if row["ref_id"] is not None:
            authors[aid]["publications"].append(
                {"id": row["ref_id"], "title": row["title"] or ""}
            )

    return authors


# ---------------------------------------------------------------------------
# Détection des paires de doublons
# ---------------------------------------------------------------------------
def find_duplicate_pairs(authors: dict[int, dict]) -> list[tuple[int, int]]:
    """
    Détecte les paires de doublons potentiels en deux étapes :
      1. Blocage par nom de famille normalisé (`Nom`) — ne compare que
         les auteurs partageant le même nom de famille.
      2. Au sein de chaque bloc, accepte la paire si :
         (a) Levenshtein(NomComplet_norm1, NomComplet_norm2) >= SEUIL, ou
         (b) is_initial_match(Prenom1, Prenom2).
    """
    # Étape 1 : blocage par nom de famille normalisé
    by_last_name: dict[str, list[dict]] = defaultdict(list)
    for auth in authors.values():
        key = normalize_name(auth.get("Nom") or "")
        if key:
            by_last_name[key].append(auth)

    pairs: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()

    # Étape 2 : comparaison au sein de chaque bloc
    for _last_name, group in by_last_name.items():
        if len(group) < 2:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a1, a2 = group[i], group[j]
                pair = (min(a1["id"], a2["id"]), max(a1["id"], a2["id"]))
                if pair in seen:
                    continue

                t1 = normalize_name(a1["NomComplet"])
                t2 = normalize_name(a2["NomComplet"])

                # Critère (a) : similarité globale du NomComplet
                if Levenshtein.ratio(t1, t2) >= SEUIL_SIMILARITE:
                    pairs.append(pair)
                    seen.add(pair)
                    continue

                # Critère (b) : initiale du prénom, nom de famille identique garanti par le blocage
                if is_initial_match(a1.get("Prenom"), a2.get("Prenom")):
                    pairs.append(pair)
                    seen.add(pair)

    return pairs


# ---------------------------------------------------------------------------
# Construction du JSON de sortie
# ---------------------------------------------------------------------------
def build_output(pairs: list[tuple[int, int]], id_to_author: dict[int, dict]) -> list[dict]:
    """
    Agrège les paires en clusters via Union-Find, utilise les publications
    déjà chargées en mémoire, et construit la liste des groupes à exporter.
    Suggestion par défaut : "keep" pour le plus petit ID, "delete" pour les autres.
    """
    uf = UnionFind()
    for id1, id2 in pairs:
        if id1 in id_to_author and id2 in id_to_author:
            uf.union(id1, id2)

    clusters = uf.clusters(list(id_to_author.keys()))
    output = []
    total = len(clusters)

    for idx, cluster in enumerate(sorted(clusters, key=lambda c: min(c)), start=1):
        print(f"  [{idx}/{total}] cluster en cours...", end="\r")
        cluster_sorted = sorted(cluster)
        keep_id = cluster_sorted[0]  # Suggestion : conserver le plus ancien ID
        nom_norm = normalize_name(id_to_author[keep_id]["NomComplet"])

        auteurs_json = [
            {
                "id": auth_id,
                "NomComplet": id_to_author[auth_id]["NomComplet"],
                "publications": id_to_author[auth_id]["publications"],
                "action": "keep" if auth_id == keep_id else "delete",
            }
            for auth_id in cluster_sorted
        ]

        output.append({"nom_normalise": nom_norm, "auteurs": auteurs_json})

    print()  # saut de ligne après la progression
    return output


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------
def main():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)

        print("Chargement des auteurs et de leurs publications...")
        id_to_author = fetch_authors_with_publications(cursor)
        print(f"{len(id_to_author)} auteurs chargés.")

        print("Détection des paires (nom de famille + initiales / Levenshtein)...")
        pairs = find_duplicate_pairs(id_to_author)
        print(f"{len(pairs)} paire(s) détectée(s).")

        print("Construction des clusters...")
        output = build_output(pairs, id_to_author)

        total_suggested = sum(
            sum(1 for a in g["auteurs"] if a["action"] == "delete")
            for g in output
        )
        print(
            f"{len(output)} groupe(s) de doublons | "
            f"{total_suggested} suppression(s) suggérée(s)."
        )

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
