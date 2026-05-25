"""
Détecte les doublons d'auteurs dont les noms sont écrits dans des alphabets
différents, par translittération vers le latin suivie d'une comparaison Levenshtein.

Cas typique : "Иванов Николай" (cyrillique) et "Ivanov Nikolai" (latin)
désignant le même auteur enregistré en double sous deux graphies distinctes.

Ce script est complémentaire des trois autres scripts de détection : il ne
traite que les paires où au moins un auteur a un nom dans un alphabet non latin
(filtre anti-doublon avec les scripts purement latins).

Pipeline de normalisation :
  1. Détection du script dominant via les plages Unicode.
  2. Translittération vers le latin :
       - `transliterate` (pip install transliterate) pour le cyrillique
         (ru, uk, bg — tous mappés sur 'ru'), le grec (el), l'arménien (hy)
         et le géorgien (ka).
       - `translit_me`  (pip install translit-me) pour l'arabe (ar) et
         l'hébreu (he), via les tables locales AR_EN / HE_EN.
  3. Normalisation standard : minuscules, sans diacritiques, sans ponctuation.

Blocage : par bi-gramme initial du nom translittéré normalisé.
Comparaison finale : ratio Levenshtein >= SEUIL_SIMILARITE.

Dépendances :
  pip install python-Levenshtein transliterate translit-me
"""

import json
import re
import unicodedata
import mysql.connector
from mysql.connector import Error as MySQLError
from collections import defaultdict
from typing import Optional
import Levenshtein

from transliterate import translit as _lat_translit
from translit_me.lang_tables import AR_EN as _AR_EN_TABLE
from translit_me.lang_tables import HE_EN as _HE_EN_TABLE
from translit_me.transliterator import transliterate as _semitic_translit

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "PASSWORD",
    "database": "DATABASE",
}
FICHIER_SORTIE_JSON = "doublons_auteurs_transliteration.json"
SEUIL_SIMILARITE = 0.85  # Ratio Levenshtein sur les noms translittérés normalisés
MIN_LEN_BLOC = 2          # Longueur du préfixe pour le blocage (bi-gramme initial)

# ---------------------------------------------------------------------------
# Détection du script dominant
# ---------------------------------------------------------------------------

# Plages Unicode des scripts non latins pris en charge
_SCRIPT_RANGES = (
    ("ru", 0x0400, 0x04FF),  # Cyrillique (ru, uk, bg — tous mappés sur 'ru')
    ("el", 0x0370, 0x03FF),  # Grec
    ("hy", 0x0530, 0x058F),  # Arménien
    ("ka", 0x10A0, 0x10FF),  # Géorgien
    ("ar", 0x0600, 0x06FF),  # Arabe
    ("he", 0x0590, 0x05FF),  # Hébreu
)

def detect_script(text: str) -> Optional[str]:
    """
    Retourne le code du script dominant dans le texte, ou None si latin/inconnu.
    Comptage par caractère sur les plages Unicode de _SCRIPT_RANGES.
    En cas d'égalité, l'ordre de la liste fait office de priorité.
    """
    counts = {lang: 0 for lang, _, _ in _SCRIPT_RANGES}
    for char in text:
        cp = ord(char)
        for lang, lo, hi in _SCRIPT_RANGES:
            if lo <= cp <= hi:
                counts[lang] += 1
                break
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else None


# ---------------------------------------------------------------------------
# Translittération vers le latin
# ---------------------------------------------------------------------------

def transliterate_to_latin(name: str, script: str) -> str:
    """
    Translittère un nom vers le latin selon son script.
    - Cyrillique/grec/arménien/géorgien : bibliothèque transliterate,
      avec reversed=True pour la direction non-latin → latin.
    - Arabe/hébreu : tables locales de translit_me.
    """
    if script in ("ru", "el", "hy", "ka"):
        return _lat_translit(name, script, reversed=True)

    if script == "ar":
        return _semitic_translit([name], _AR_EN_TABLE)[0]

    if script == "he":
        return _semitic_translit([name], _HE_EN_TABLE)[0]

    return name


def normalize_translit(text: str) -> str:
    """
    Normalisation post-translittération : minuscules, sans diacritiques ni ponctuation.
    (\w est unicode-aware par défaut en Python 3)
    """
    s = str(text).lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^\w\s]", " ", s)
    return " ".join(s.split())


def get_translit_norm(name: Optional[str]) -> tuple[str, bool]:
    """
    Pipeline complet : détection du script → translittération → normalisation.
    Retourne (nom_normalisé, est_non_latin).
    est_non_latin = True si une translittération a été appliquée ;
    utilisé pour filtrer les paires purement latines.
    """
    if not name:
        return "", False
    script = detect_script(name)
    is_non_latin = script is not None
    if is_non_latin:
        name = transliterate_to_latin(name, script)
    return normalize_translit(name), is_non_latin


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
    Détecte les paires de doublons potentiels en trois étapes :

      1. Translittération de tous les NomComplet vers le latin normalisé.
         L'indicateur _is_non_latin est stocké dans chaque auteur.

      2. Blocage par bi-gramme initial du nom translittéré : réduit les
         comparaisons à celles dont les deux premiers caractères coïncident.

      3. Dans chaque bloc, accepte la paire si :
         (a) au moins un auteur a un nom non latin — filtre de complémentarité
             avec les scripts de détection purement latins ;
         (b) Levenshtein(translit1, translit2) >= SEUIL_SIMILARITE.
    """
    # Étape 1 : translittération de tous les auteurs
    total = len(authors)
    non_latin_count = 0
    for idx, auth in enumerate(authors.values(), start=1):
        if idx % 500 == 0 or idx == total:
            print(f"  Translittération : {idx}/{total}...", end="\r")
        t, is_nl = get_translit_norm(auth["NomComplet"])
        auth["_translit"] = t
        auth["_is_non_latin"] = is_nl
        if is_nl:
            non_latin_count += 1
    print(f"\n  {non_latin_count} auteur(s) avec un nom non latin détecté(s).")

    # Étape 2 : blocage par bi-gramme initial du nom translittéré
    by_prefix: dict[str, list[dict]] = defaultdict(list)
    for auth in authors.values():
        prefix = auth["_translit"][:MIN_LEN_BLOC]
        if len(prefix) == MIN_LEN_BLOC:
            by_prefix[prefix].append(auth)

    pairs: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()

    # Étape 3 : comparaison au sein de chaque bloc
    for _prefix, group in by_prefix.items():
        if len(group) < 2:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a1, a2 = group[i], group[j]

                # Filtre (a) : au moins un nom non latin
                if not a1["_is_non_latin"] and not a2["_is_non_latin"]:
                    continue

                pair = (min(a1["id"], a2["id"]), max(a1["id"], a2["id"]))
                if pair in seen:
                    continue

                # Critère (b) : Levenshtein sur les formes translittérées normalisées
                if Levenshtein.ratio(a1["_translit"], a2["_translit"]) >= SEUIL_SIMILARITE:
                    pairs.append(pair)
                    seen.add(pair)

    return pairs


# ---------------------------------------------------------------------------
# Construction du JSON de sortie
# ---------------------------------------------------------------------------

def build_output(pairs: list[tuple[int, int]], id_to_author: dict[int, dict]) -> list[dict]:
    """
    Agrège les paires en clusters (Union-Find), utilise les publications
    déjà chargées en mémoire, et construit la liste des groupes à exporter.
    Le champ "NomTranslit" (indicatif, non requis par le script d'application)
    facilite la vérification manuelle des décisions.
    Suggestion par défaut : "keep" pour le plus petit ID.
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
        keep_id = cluster_sorted[0]
        nom_norm = id_to_author[keep_id].get("_translit", "")

        auteurs_json = [
            {
                "id": auth_id,
                "NomComplet": id_to_author[auth_id]["NomComplet"],
                "NomTranslit": id_to_author[auth_id].get("_translit", ""),  # aide à la vérification manuelle
                "publications": id_to_author[auth_id]["publications"],
                "action": "keep" if auth_id == keep_id else "delete",
            }
            for auth_id in cluster_sorted
        ]

        output.append({"nom_normalise": nom_norm, "auteurs": auteurs_json})

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
        id_to_author = fetch_authors_with_publications(cursor)
        print(f"{len(id_to_author)} auteurs chargés.")

        pairs = find_duplicate_pairs(id_to_author)
        print(f"{len(pairs)} paire(s) détectée(s).")

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
            "Vérifiez les champs 'action' (keep / delete / skip) avant de lancer\n"
            "_appliquer_doublons_auteurs.py.\n"
        )

        cursor.close()
        conn.close()

    except MySQLError as err:
        print(f"Erreur MySQL : {err}")


if __name__ == "__main__":
    main()