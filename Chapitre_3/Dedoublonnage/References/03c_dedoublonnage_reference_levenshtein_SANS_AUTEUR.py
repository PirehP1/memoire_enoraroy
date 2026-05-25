"""
Détecte les doublons de références par similarité de titre.

DOI et ISSN ont déjà été traités en amont — ce script n'y touche pas.

Pipeline de filtrage (trois passes successives, chacune réduisant le périmètre) :
  1. Année exacte        — seules les références partageant la même année sont comparées.
                           Les références sans année forment un groupe séparé entre elles.
  2. Secondary title     — Levenshtein normalisé ≥ SEUIL_SECONDARY_TITLE.
  3. Titre principal     — Levenshtein normalisé ≥ SEUIL_TITLE.
  4. Clusters            — Union-Find pour la transitivité.
  5. Export JSON         — candidats à vérifier/corriger manuellement avant fusion.
  
Pour des raisons de rapidité de calcul, à exécuter APRES celui qui a déjà détecté les doublons avec les auteurs ! et pour appliquer les fusions, juste changer le nom du fichier json dans le script d'application
"""

import json
import re
import unicodedata
import mysql.connector
from mysql.connector import Error as MySQLError
from collections import defaultdict
import Levenshtein

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "PASSWORD",
    "database": "DATABASE",
}

FICHIER_SORTIE_JSON = "doublons_titre_SANS_auteur_a_verifier.json"

# Seuil Levenshtein pour le secondary_title (regroupement large)
SEUIL_SECONDARY_TITLE = 0.85
# Seuil Levenshtein pour le titre principal (comparaison fine)
SEUIL_TITLE           = 0.88

# Titres normalisés à exclure explicitement (revues génériques, listes, etc.)
TITRES_EXCLUS: set[str] = set()


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

def normalize(text) -> str:
    """Minuscule, sans accents, sans ponctuation, espaces normalisés."""
    if not text:
        return ""
    nfd = unicodedata.normalize("NFKD", str(text))
    s   = "".join(c for c in nfd if not unicodedata.combining(c)).lower()
    s   = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def lev_ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return Levenshtein.ratio(a, b)


# ---------------------------------------------------------------------------
# Union-Find
# ---------------------------------------------------------------------------

class UnionFind:
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
        groups: dict[int, list[int]] = defaultdict(list)
        for i in ids:
            groups[self.find(i)].append(i)
        return [v for v in groups.values() if len(v) > 1]


# ---------------------------------------------------------------------------
# Accès base de données
# ---------------------------------------------------------------------------

def fetch_references(cursor) -> list[dict]:
    cursor.execute(
        "SELECT id, title, secondary_title, year "
        "FROM reference "
        "WHERE title IS NOT NULL AND title != ''"
    )
    return cursor.fetchall()


# ---------------------------------------------------------------------------
# Passes de filtrage
# ---------------------------------------------------------------------------

def group_by_year(refs: list[dict]) -> list[list[dict]]:
    """
    Passe 1 — regroupement par année exacte.
    Les références sans année sont isolées dans un groupe unique entre elles.
    Ne retourne que les groupes d'au moins 2 références.
    """
    buckets: dict[str, list[dict]] = defaultdict(list)
    for r in refs:
        year = str(r["year"]).strip() if r.get("year") is not None else "__no_year__"
        buckets[year].append(r)
    return [v for v in buckets.values() if len(v) >= 2]


def group_by_secondary_title(refs: list[dict]) -> list[list[dict]]:
    """
    Passe 2 — regroupement glouton par secondary_title (Levenshtein).
    Les références sans secondary_title sont exclues.
    """
    buckets: list[list[dict]] = []
    keys: list[str]           = []

    for r in refs:
        norm = normalize(r.get("secondary_title") or "")
        if not norm:
            continue
        for i, key in enumerate(keys):
            if lev_ratio(norm, key) >= SEUIL_SECONDARY_TITLE:
                buckets[i].append(r)
                break
        else:
            buckets.append([r])
            keys.append(norm)

    return [b for b in buckets if len(b) >= 2]


def find_title_clusters(refs: list[dict]) -> list[list[dict]]:
    """
    Passe 3 — comparaison des titres principaux uniquement.
    Construit les clusters par Union-Find pour gérer la transitivité.
    """
    uf = UnionFind()
    n  = len(refs)

    for i in range(n):
        for j in range(i + 1, n):
            r1, r2 = refs[i], refs[j]

            t1 = normalize(r1.get("title") or "")
            t2 = normalize(r2.get("title") or "")
            if lev_ratio(t1, t2) < SEUIL_TITLE:
                continue

            uf.union(r1["id"], r2["id"])

    id_to_ref = {r["id"]: r for r in refs}
    return [
        [id_to_ref[i] for i in cluster]
        for cluster in uf.clusters([r["id"] for r in refs])
    ]


# ---------------------------------------------------------------------------
# Construction du JSON de sortie
# ---------------------------------------------------------------------------

def build_output(clusters: list[list[dict]]) -> list[dict]:
    """
    Suggestion par défaut : on conserve le plus petit ID (le plus ancien en base).
    Valeurs d'action acceptées par appliquer_fusions_titre_auteur.py :
      keep | delete | skip
    """
    output = []
    for cid, refs in enumerate(clusters, start=1):
        refs_sorted = sorted(refs, key=lambda r: r["id"])
        keep_id     = refs_sorted[0]["id"]
        output.append({
            "cluster_id": cid,
            "references": [
                {
                    "id":               r["id"],
                    "title":            r.get("title") or "",
                    "secondary_title":  r.get("secondary_title") or "",
                    "year":             r.get("year"),
                    "action":           "keep" if r["id"] == keep_id else "delete",
                }
                for r in refs_sorted
            ],
        })
    return output


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def main():
    try:
        conn   = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)

        rows = fetch_references(cursor)
        print(f"{len(rows)} références récupérées.")

        if TITRES_EXCLUS:
            rows = [r for r in rows if normalize(r.get("title")) not in TITRES_EXCLUS]

        # Passe 1 — année exacte
        year_groups = group_by_year(rows)
        print(f"Passe 1 (année)           : {len(year_groups)} groupe(s).")

        # Passe 2 — secondary_title
        st_buckets: list[list[dict]] = []
        for yg in year_groups:
            st_buckets.extend(group_by_secondary_title(yg))
        print(f"Passe 2 (secondary_title) : {len(st_buckets)} bucket(s).")

        # Passe 3 — titre uniquement → clusters
        all_clusters: list[list[dict]] = []
        for bucket in st_buckets:
            all_clusters.extend(find_title_clusters(bucket))
        print(f"Passe 3 (titre)           : {len(all_clusters)} cluster(s) détectés.")

        output = build_output(all_clusters)

        with open(FICHIER_SORTIE_JSON, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2, default=str)

        total_sugg = sum(
            sum(1 for r in g["references"] if r["action"] == "delete")
            for g in output
        )
        print(f"\nJSON exporté → {FICHIER_SORTIE_JSON}")
        print(f"{total_sugg} suppression(s) suggérées sur {len(output)} cluster(s).")
        print("Vérifiez et ajustez les 'action' (keep/delete/skip) avant fusion.")

        cursor.close()
        conn.close()

    except MySQLError as err:
        print(f"Erreur MySQL : {err}")


if __name__ == "__main__":
    main()