"""
Fusionne les auteurs doublons détectés par identifiants partagés
(PPN_IDREF, PPN_VIAF, wikipedia, orcid, scopusid).

Pour chaque groupe de doublons :
  - Détecte les conflits d'identifiants (deux valeurs différentes pour
    le même champ au sein du groupe) → log + skip
  - Sinon, conserve l'auteur avec le plus de publications (X),
    lui transfère les identifiants manquants depuis ses doublons,
    redirige les liens ecriture, supprime les doublons.

Produit un fichier log : fusion_identifiants.log
"""

import mysql.connector
from mysql.connector import Error as MySQLError
from collections import defaultdict
from datetime import datetime

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "PASSWORD",
    "database": "DATABASE",
}

LOG_FILE = "fusion_identifiants.log"

# True  → affiche ce qui serait fait, sans écrire en base
# False → applique les modifications réelles
DRY_RUN = True

# Identifiants sur lesquels on détecte les doublons -> ajouter autant que nécessaires selon l'état de la bdds
ID_FIELDS = ["PPN_IDREF", "PPN_VIAF"]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

_log_lines = []

def log(msg: str) -> None:
    print(msg)
    _log_lines.append(msg)

def save_log() -> None:
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(f"=== Fusion doublons — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
        f.write(f"DRY_RUN = {DRY_RUN}\n\n")
        f.write("\n".join(_log_lines))

# ---------------------------------------------------------------------------
# Union-Find
# ---------------------------------------------------------------------------

class UnionFind:
    def __init__(self):
        self._p = {}

    def find(self, x):
        self._p.setdefault(x, x)
        if self._p[x] != x:
            self._p[x] = self.find(self._p[x])
        return self._p[x]

    def union(self, x, y):
        rx, ry = self.find(x), self.find(y)
        if rx != ry:
            self._p[max(rx, ry)] = min(rx, ry)

    def clusters(self, ids):
        groups = defaultdict(list)
        for i in ids:
            groups[self.find(i)].append(i)
        return [v for v in groups.values() if len(v) >= 2]

# ---------------------------------------------------------------------------
# Groupement des doublons
# ---------------------------------------------------------------------------

def group_duplicates(authors: list) -> list:
    """
    Regroupe les auteurs partageant au moins un identifiant commun (non nul).
    Retourne une liste de groupes (chaque groupe = liste de dicts auteur).
    """
    uf = UnionFind()
    id_to_author_ids = defaultdict(list)  # (champ, valeur) → [author_id, ...]

    for a in authors:
        for field in ID_FIELDS:
            val = a.get(field)
            if val:
                id_to_author_ids[(field, val)].append(a["id"])

    for author_ids in id_to_author_ids.values():
        for i in range(1, len(author_ids)):
            uf.union(author_ids[0], author_ids[i])

    id_map = {a["id"]: a for a in authors}
    clusters = uf.clusters([a["id"] for a in authors])
    return [[id_map[aid] for aid in cluster] for cluster in clusters]

# ---------------------------------------------------------------------------
# Détection des conflits
# ---------------------------------------------------------------------------

def find_conflicts(group: list) -> list:
    """
    Retourne la liste des messages de conflit pour un groupe.
    Conflit = deux auteurs du groupe ont des valeurs différentes (toutes non nulles)
    pour le même champ identifiant.
    """
    conflicts = []
    for field in ID_FIELDS:
        values = {a[field] for a in group if a.get(field)}
        if len(values) > 1:
            detail = ", ".join(
                f"id={a['id']} ({a['NomComplet']}) → {a[field]}"
                for a in group if a.get(field)
            )
            conflicts.append(f"  Conflit sur {field} : {detail}")
    return conflicts

# ---------------------------------------------------------------------------
# Fusion d'un groupe
# ---------------------------------------------------------------------------

def pub_count(cursor, author_id: int) -> int:
    cursor.execute(
        "SELECT COUNT(*) AS n FROM ecriture WHERE author_id = %s",
        (author_id,)
    )
    return cursor.fetchone()["n"]


def merge_group(cursor, group: list) -> dict:
    """
    Fusionne un groupe sans conflit.
    Retourne un résumé de l'opération.
    """
    # Auteur conservé = celui avec le plus de publications
    counts = {a["id"]: pub_count(cursor, a["id"]) for a in group}
    keeper = max(group, key=lambda a: counts[a["id"]])
    duplicates = [a for a in group if a["id"] != keeper["id"]]

    identifiers_added = []
    links_redirected = 0
    links_dropped = 0

    # Publications déjà liées à l'auteur conservé
    cursor.execute(
        "SELECT reference_id FROM ecriture WHERE author_id = %s",
        (keeper["id"],)
    )
    keeper_refs = {row["reference_id"] for row in cursor.fetchall()}

    for dup in duplicates:

        # -- 1. Transfert des identifiants manquants vers le keeper --
        fields_to_update = {}
        for field in ID_FIELDS:
            if not keeper.get(field) and dup.get(field):
                fields_to_update[field] = dup[field]

        if fields_to_update and not DRY_RUN:
            set_clause = ", ".join(f"`{f}` = %s" for f in fields_to_update)
            values = list(fields_to_update.values()) + [keeper["id"]]
            cursor.execute(
                f"UPDATE authors SET {set_clause} WHERE id = %s",
                values
            )

        for f, v in fields_to_update.items():
            identifiers_added.append(f"{f}={v}")
        keeper.update(fields_to_update)  # mise à jour locale pour les passes suivantes

        # -- 2. Liens ecriture du doublon --
        cursor.execute(
            "SELECT id, reference_id FROM ecriture WHERE author_id = %s",
            (dup["id"],)
        )
        dup_rows = cursor.fetchall()

        for row in dup_rows:
            if row["reference_id"] in keeper_refs:
                # Déjà lié au keeper : suppression du lien en double
                if not DRY_RUN:
                    cursor.execute("DELETE FROM ecriture WHERE id = %s", (row["id"],))
                links_dropped += 1
            else:
                # Pas encore lié : redirection vers le keeper
                if not DRY_RUN:
                    cursor.execute(
                        "UPDATE ecriture SET author_id = %s WHERE id = %s",
                        (keeper["id"], row["id"])
                    )
                keeper_refs.add(row["reference_id"])
                links_redirected += 1

        # -- 3. Suppression du doublon --
        if not DRY_RUN:
            cursor.execute("DELETE FROM authors WHERE id = %s", (dup["id"],))

    return {
        "keeper_id": keeper["id"],
        "keeper_name": keeper["NomComplet"],
        "keeper_pubs": counts[keeper["id"]],
        "duplicates": [
            {"id": d["id"], "name": d["NomComplet"], "pubs": counts[d["id"]]}
            for d in duplicates
        ],
        "identifiers_added": identifiers_added,
        "links_redirected": links_redirected,
        "links_dropped": links_dropped,
        "n_deleted": len(duplicates),
    }

# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def main():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)

        # Chargement de tous les auteurs ayant au moins un identifiant
        fields = ", ".join(f"`{f}`" for f in ID_FIELDS)
        where = " OR ".join(f"`{f}` IS NOT NULL" for f in ID_FIELDS)
        cursor.execute(f"SELECT id, NomComplet, {fields} FROM authors WHERE {where}")
        authors = cursor.fetchall()
        log(f"Auteurs avec au moins un identifiant : {len(authors)}")

        groups = group_duplicates(authors)
        log(f"Groupes de doublons détectés : {len(groups)}\n")

        merged = 0
        skipped_conflict = 0
        total_deleted = 0
        total_redirected = 0

        for group in groups:
            names = ", ".join(f"{a['NomComplet']} (id={a['id']})" for a in group)

            conflicts = find_conflicts(group)
            if conflicts:
                log(f"[CONFLIT] Groupe ignoré : {names}")
                for c in conflicts:
                    log(c)
                log("")
                skipped_conflict += 1
                continue

            result = merge_group(cursor, group)
            prefix = "[DRY RUN] " if DRY_RUN else ""
            log(
                f"{prefix}[FUSION] Conservé : {result['keeper_name']} "
                f"(id={result['keeper_id']}, {result['keeper_pubs']} pub(s))"
            )
            for d in result["duplicates"]:
                log(f"  Supprimé : {d['name']} (id={d['id']}, {d['pubs']} pub(s))")
            if result["identifiers_added"]:
                log(f"  Identifiants transférés : {', '.join(result['identifiers_added'])}")
            log(
                f"  Liens ecriture : {result['links_redirected']} redirigé(s), "
                f"{result['links_dropped']} doublon(s) supprimé(s)"
            )
            log("")

            merged += 1
            total_deleted += result["n_deleted"]
            total_redirected += result["links_redirected"]

        if not DRY_RUN:
            conn.commit()
            log("Commit effectué.")

        log("=" * 60)
        log(f"Groupes fusionnés    : {merged}")
        log(f"Groupes en conflit   : {skipped_conflict}")
        log(f"Auteurs supprimés    : {total_deleted}")
        log(f"Liens redirigés      : {total_redirected}")
        if DRY_RUN:
            log("\n*** DRY RUN — aucune modification appliquée ***")
            log("Passez DRY_RUN = False pour appliquer.")

        cursor.close()
        conn.close()

    except MySQLError as err:
        log(f"Erreur MySQL : {err}")
        if "conn" in dir():
            conn.rollback()

    finally:
        save_log()
        print(f"\nLog écrit dans : {LOG_FILE}")


if __name__ == "__main__":
    main()