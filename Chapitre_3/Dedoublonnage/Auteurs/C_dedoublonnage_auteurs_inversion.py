"""
Détecte les doublons d'auteurs par inversion des composantes du nom
et par présence/absence d'initiales.

Logique de détection :
  Deux auteurs partagent potentiellement la même identité si leurs noms
  contiennent les mêmes tokens une fois triés, indépendamment de leur
  ordre d'écriture.
  Ex. : "Dupont, Jean" et "Jean Dupont" → tokens triés identiques.

  Deux signatures sont calculées par auteur :
    - Signature complète  : tous les tokens normalisés, triés alphabétiquement.
    - Signature minimale  : idem, en excluant les tokens de longueur 1
                            (initiales isolées comme "J.").
      Ex. : "Dupont J." → tokens ["dupont", "j"] → minimale = "dupont".

  Stratégie de blocage : groupement par signature minimale (critère large),
  puis filtrage par ratio Levenshtein sur les signatures complètes >= SEUIL.
  Le Levenshtein capte les légères variations orthographiques
  (double consonne, accent résiduel) que le tri seul ne suffit pas à aligner.

Union-Find : garantit la transitivité des paires détectées.

Sortie JSON :
  [
    {
      "nom_normalise": "dupont jean",   ← signature minimale du groupe
      "auteurs": [
        { "id": 1,  "NomComplet": "Dupont, Jean",
          "publications": [...], "action": "keep" },
        { "id": 12, "NomComplet": "Jean Dupont",
          "publications": [...], "action": "delete" }
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
FICHIER_SORTIE_JSON = "doublons_auteurs_inversion.json"
SEUIL_SIMILARITE = 0.85  # Ratio Levenshtein sur les signatures complètes
MIN_LEN_SIGNATURE = 4    # Longueur minimale de la signature minimale (évite les noms trop courts)


# ---------------------------------------------------------------------------
# Normalisation et signatures
# ---------------------------------------------------------------------------
def normalize_tokens(name: Optional[str]) -> list[str]:
    """
    Découpe un NomComplet en tokens normalisés :
      1. Mise en minuscules.
      2. Décomposition NFD et suppression des diacritiques.
      3. Suppression de tout ce qui n'est pas une lettre unicode ou un espace.
         (\w est unicode-aware par défaut en Python 3)
      4. Découpage en tokens non vides.
    """
    if not name:
        return []
    s = str(name).lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^\w\s]", " ", s)
    return [t for t in s.split() if t]


def full_signature(tokens: list[str]) -> str:
    """Signature triée de tous les tokens (capture les inversions)."""
    return " ".join(sorted(tokens))


def minimal_signature(tokens: list[str]) -> str:
    """
    Signature triée des seuls tokens de longueur > 1 (ignore les initiales).
    Repli sur la signature complète si le filtrage vide la liste.
    """
    filtered = [t for t in tokens if len(t) > 1]
    if not filtered:
        return full_signature(tokens)
    return " ".join(sorted(filtered))


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
# Détection des paires de doublons
# ---------------------------------------------------------------------------
def find_duplicate_pairs(authors: dict[int, dict]) -> list[tuple[int, int]]:
    """
    Détecte les paires de doublons potentiels en deux étapes :

      1. Calcul des signatures (complète et minimale) pour chaque auteur.
         Les signatures sont stockées directement dans le dict de l'auteur
         pour éviter un double calcul lors de la construction du JSON.

      2. Blocage par signature minimale : les auteurs partageant la même
         signature minimale sont candidats doublons (inversions ou initiales
         manquantes). Au sein de chaque bloc, la paire est retenue si le ratio
         Levenshtein entre leurs signatures complètes >= SEUIL_SIMILARITE.

    Pourquoi Levenshtein sur les signatures complètes et non sur NomComplet ?
    Le tri des tokens neutralise les inversions avant la comparaison, rendant
    la distance de Levenshtein efficace sur les seules variations résiduelles
    (orthographe, double lettre, etc.).
    """
    # Étape 1 : calcul des signatures pour tous les auteurs
    for auth in authors.values():
        tokens = normalize_tokens(auth["NomComplet"])
        auth["_full_sig"] = full_signature(tokens)
        auth["_min_sig"] = minimal_signature(tokens)

    # Étape 2 : blocage par signature minimale
    by_min_sig: dict[str, list[dict]] = defaultdict(list)
    for auth in authors.values():
        if len(auth["_min_sig"]) >= MIN_LEN_SIGNATURE:
            by_min_sig[auth["_min_sig"]].append(auth)

    pairs: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()

    for _sig, group in by_min_sig.items():
        if len(group) < 2:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a1, a2 = group[i], group[j]
                pair = (min(a1["id"], a2["id"]), max(a1["id"], a2["id"]))
                if pair in seen:
                    continue
                # Levenshtein sur les signatures complètes (tokens triés)
                if Levenshtein.ratio(a1["_full_sig"], a2["_full_sig"]) >= SEUIL_SIMILARITE:
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
    Le champ "nom_normalise" reprend la signature minimale du représentant du cluster.
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

        # Signature minimale du représentant comme clé lisible du groupe
        nom_norm = id_to_author[keep_id].get("_min_sig", "")

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

        print("Détection des paires (inversions / initiales manquantes / Levenshtein)...")
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