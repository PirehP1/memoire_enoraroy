"""
Détecte les doublons de références par similarité de titre avec contenance.

Apports par rapport aux scripts Levenshtein existants :
  - Détection par contenance : le titre court est littéralement contenu dans
    le titre long (min. 10 caractères), indépendamment du ratio Levenshtein.
  - Références sans secondary_title : incluses dans une phase catch-all,
    comparées contre tout le corpus (les scripts existants les ignoraient).
  - Références sans année : incluses dans le catch-all, comparées sans
    contrainte d'année (les scripts existants les isolaient entre elles).
  - Secondary_title utilisé comme filtre d'exclusion (<20%) plutôt que
    comme critère de regroupement, ce qui est plus permissif.

DOI et ISSN ont déjà été traités en amont — ce script n'y touche pas.

Pipeline :
  1. Partition : main stream (année + secondary_title présents) / catch-all.
  2. Main stream  — groupement par année (±1 an), exclusion si secondary_title
                    des deux < 20%, comparaison titre ≥ SEUIL ou contenance.
  3. Catch-all    — comparaison de chaque référence contre tout le corpus,
                    mêmes critères titre, année ignorée.
  4. Union-Find   — transitivité des paires détectées.
  5. Export JSON  — à vérifier/corriger manuellement avant fusion.

Valeurs d'action dans le JSON : keep | delete | skip
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

FICHIER_SORTIE_JSON = "doublons_contenance_a_verifier.json"

# Seuil Levenshtein pour le titre principal
SEUIL_TITLE = 0.85
# Seuil d'exclusion pour le secondary_title (si les deux en ont un)
SEUIL_SECONDARY_EXCLUSION = 0.20
# Longueur minimale du titre court pour la détection par contenance
MIN_LEN_CONTAINMENT = 10


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


def titles_match(t1: str, t2: str) -> bool:
    """
    True si :
      - ratio Levenshtein >= SEUIL_TITLE, ou
      - le titre le plus court est contenu dans le plus long (min MIN_LEN_CONTAINMENT).
    """
    if not t1 or not t2:
        return False
    if lev_ratio(t1, t2) >= SEUIL_TITLE:
        return True
    shorter, longer = (t1, t2) if len(t1) <= len(t2) else (t2, t1)
    if len(shorter) >= MIN_LEN_CONTAINMENT and shorter in longer:
        return True
    return False


def secondary_titles_excluded(s1: str, s2: str) -> bool:
    """
    True si les deux secondary_titles existent et sont trop dissemblables
    (ratio < SEUIL_SECONDARY_EXCLUSION sans contenance) → paire à ignorer.
    """
    if not s1 or not s2:
        return False  # information absente = non bloquant
    if lev_ratio(s1, s2) >= SEUIL_SECONDARY_EXCLUSION:
        return False
    shorter = s1 if len(s1) <= len(s2) else s2
    longer  = s2 if len(s1) <= len(s2) else s1
    if len(shorter) >= MIN_LEN_CONTAINMENT and shorter in longer:
        return False
    return True  # trop dissemblables → exclure


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
        "WHERE title IS NOT NULL AND title != '' "
        "AND title NOT LIKE '%intro%' "
        "AND title NOT LIKE '%preface%' "
        "AND title NOT LIKE '%prologue%' "
        "AND title NOT LIKE '%epilogue%' "
        "AND title NOT LIKE '%abbrevia%' "
        "AND title NOT LIKE '%conclu%' "
        "AND title NOT LIKE '%index%' "
        "AND title NOT LIKE 'rezension von%' "
        "AND title NOT LIKE '%review%' "
        "ORDER BY id ASC"
    )
    return cursor.fetchall()


# ---------------------------------------------------------------------------
# Partition
# ---------------------------------------------------------------------------

def partition(refs: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Main stream : année présente ET secondary_title présent.
    Catch-all   : l'un ou l'autre absent.
    """
    main, catch = [], []
    for r in refs:
        has_year = r.get("year") is not None and str(r["year"]).strip() != ""
        has_sec  = bool(normalize(r.get("secondary_title") or ""))
        if has_year and has_sec:
            main.append(r)
        else:
            catch.append(r)
    return main, catch


# ---------------------------------------------------------------------------
# Phase 1 — Main stream (groupement par année ±1)
# ---------------------------------------------------------------------------

def find_pairs_main(refs: list[dict]) -> list[tuple[int, int]]:
    """
    Groupe par année (±1 an), applique l'exclusion secondary_title,
    détecte les paires par similarité/contenance de titre.
    """
    by_year: dict[int, list[dict]] = defaultdict(list)
    for r in refs:
        try:
            by_year[int(r["year"])].append(r)
        except (TypeError, ValueError):
            pass

    pairs: list[tuple[int, int]] = []
    years = sorted(by_year)
    total_years = len(years)

    for i, y in enumerate(years, start=1):
        if i % 5 == 0 or i == total_years:
            print(f"  Phase 1 : {i}/{total_years} années traitées, {len(pairs)} paire(s) trouvée(s)...", end="\r")

        for y2 in [y, y + 1]:
            group2 = by_year.get(y2, [])
            group1 = by_year[y]
            for ri, r1 in enumerate(group1):
                start = ri + 1 if y2 == y else 0
                for r2 in group2[start:]:
                    s1 = normalize(r1.get("secondary_title") or "")
                    s2 = normalize(r2.get("secondary_title") or "")
                    if secondary_titles_excluded(s1, s2):
                        continue
                    t1 = normalize(r1.get("title") or "")
                    t2 = normalize(r2.get("title") or "")
                    if titles_match(t1, t2):
                        pairs.append((r1["id"], r2["id"]))

    print()  # saut de ligne après le \r
    return pairs


# ---------------------------------------------------------------------------
# Phase 2 — Catch-all (comparaison contre tout le corpus)
# ---------------------------------------------------------------------------

def find_pairs_catch(catch_refs: list[dict], all_refs: list[dict]) -> list[tuple[int, int]]:
    """
    Chaque référence du catch-all est comparée à toutes les références
    (y compris celles du main stream). L'année est ignorée.
    La paire (min_id, max_id) garantit l'unicité.
    """
    seen: set[tuple[int, int]] = set()
    pairs: list[tuple[int, int]] = []
    total = len(catch_refs)

    for idx, r1 in enumerate(catch_refs, start=1):
        if idx % 50 == 0 or idx == total:
            print(f"  Phase 2 : {idx}/{total} références catch-all traitées, {len(pairs)} paire(s) trouvée(s)...", end="\r")

        t1 = normalize(r1.get("title") or "")
        s1 = normalize(r1.get("secondary_title") or "")
        for r2 in all_refs:
            if r2["id"] == r1["id"]:
                continue
            key = (min(r1["id"], r2["id"]), max(r1["id"], r2["id"]))
            if key in seen:
                continue
            s2 = normalize(r2.get("secondary_title") or "")
            if secondary_titles_excluded(s1, s2):
                seen.add(key)
                continue
            t2 = normalize(r2.get("title") or "")
            if titles_match(t1, t2):
                pairs.append(key)
            seen.add(key)

    print()  # saut de ligne après le \r
    return pairs


# ---------------------------------------------------------------------------
# Construction du JSON de sortie
# ---------------------------------------------------------------------------

def build_clusters(pairs: list[tuple[int, int]], id_to_ref: dict[int, dict]) -> list[list[dict]]:
    uf = UnionFind()
    for id1, id2 in pairs:
        if id1 in id_to_ref and id2 in id_to_ref:
            uf.union(id1, id2)
    return [
        [id_to_ref[i] for i in cluster if i in id_to_ref]
        for cluster in uf.clusters(list(id_to_ref))
    ]


def build_output(clusters: list[list[dict]]) -> list[dict]:
    output = []
    for cid, refs in enumerate(clusters, start=1):
        if len(refs) < 2:
            continue
        refs_sorted = sorted(refs, key=lambda r: r["id"])
        keep_id = refs_sorted[0]["id"]
        output.append({
            "cluster_id": cid,
            "references": [
                {
                    "id":              r["id"],
                    "title":           r.get("title") or "",
                    "secondary_title": r.get("secondary_title") or "",
                    "year":            r.get("year"),
                    "action":          "keep" if r["id"] == keep_id else "delete",
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

        print("Récupération des références...")
        rows = fetch_references(cursor)
        print(f"{len(rows)} références récupérées.")

        main_refs, catch_refs = partition(rows)
        print(f"Partition : {len(main_refs)} main stream, {len(catch_refs)} catch-all.\n")

        print("Phase 1 — main stream (année ±1)...")
        pairs_main = find_pairs_main(main_refs)
        print(f"Phase 1 terminée : {len(pairs_main)} paire(s) détectée(s).\n")

        print("Phase 2 — catch-all (comparaison exhaustive)...")
        pairs_catch = find_pairs_catch(catch_refs, rows)
        print(f"Phase 2 terminée : {len(pairs_catch)} paire(s) détectée(s).\n")

        all_pairs = pairs_main + pairs_catch
        print(f"Total : {len(all_pairs)} paire(s) avant transitivité.")

        print("Construction des clusters (Union-Find)...")
        id_to_ref = {r["id"]: r for r in rows}
        clusters  = build_clusters(all_pairs, id_to_ref)
        clusters  = [c for c in clusters if len(c) >= 2]
        print(f"Clusters après transitivité : {len(clusters)}.\n")

        print("Export JSON...")
        output = build_output(clusters)

        with open(FICHIER_SORTIE_JSON, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2, default=str)

        total_sugg = sum(
            sum(1 for r in g["references"] if r["action"] == "delete")
            for g in output
        )
        print(f"JSON exporté → {FICHIER_SORTIE_JSON}")
        print(f"{total_sugg} suppression(s) suggérée(s) sur {len(output)} cluster(s).")
        print("Vérifiez et ajustez les 'action' (keep/delete/skip) avant fusion.")

        cursor.close()
        conn.close()

    except MySQLError as err:
        print(f"Erreur MySQL : {err}")


if __name__ == "__main__":
    main()