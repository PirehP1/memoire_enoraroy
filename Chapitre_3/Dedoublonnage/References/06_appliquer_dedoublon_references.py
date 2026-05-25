"""
Applique les fusions issues de n'importe quel fichier JSON de dédoublonnage.

Usage :
    python appliquer_dedoublon.py <fichier_decisions.json> [--apply]

    Sans --apply → mode DRY RUN (affiche ce qui serait fait, sans toucher la base)
    Avec --apply → applique les modifications réelles

Règles de lecture du JSON :
  - "action": "keep"   → référence conservée (reçoit la fusion de tous les champs)
  - "action": "delete" → supprimée après fusion
  - "action": "skip"   → cluster/groupe entier ignoré

Un cluster sans exactement un "keep" est ignoré avec un avertissement.

Champs fusionnés avant suppression :
  - disponibilite_persee, dispo_JSTOR, disponibilite_cairn   → valeur maximale
  - fiabilite_disponibilite_persee, fiabilite_dispo_jstor,
    fiabilite_disponibilite_cairn                            → suit le meilleur score de dispo
  - year                                                     → valeur la plus ancienne
  - date_modified                                            → mis à NOW() si au moins un champ change
  - reference_keyword                                        → mots-clés transférés vers le keep
"""

import argparse
import json
import sys
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

# Paires (champ de disponibilité, champ de fiabilité associé).
# La fiabilité suit toujours la notice qui apporte la meilleure disponibilité.
AVAILABILITY_PAIRS: list[tuple[str, str]] = [
    ("disponibilite_persee",  "fiabilite_disponibilite_persee"),
    ("dispo_JSTOR",           "fiabilite_dispo_jstor"),
    ("disponibilite_cairn",   "fiabilite_disponibilite_cairn"),
]


# ---------------------------------------------------------------------------
# Validation du cluster
# ---------------------------------------------------------------------------

def validate_cluster(cluster: dict) -> tuple[int | None, list[int], bool]:
    """
    Analyse un cluster et retourne :
      - keep_id    : ID à conserver (None si invalide ou skip)
      - delete_ids : liste des IDs à supprimer
      - skip       : True si le cluster doit être ignoré silencieusement
    """
    refs = cluster.get("references", [])

    if any(r.get("action") == "skip" for r in refs):
        return None, [], True

    keeps   = [r["id"] for r in refs if r.get("action") == "keep"]
    deletes = [r["id"] for r in refs if r.get("action") == "delete"]

    if len(keeps) != 1:
        return None, [], False   # invalide → avertissement côté appelant

    return keeps[0], deletes, False


# ---------------------------------------------------------------------------
# Opérations en base
# ---------------------------------------------------------------------------

def fetch_refs(cursor, ids: list[int]) -> dict[int, dict]:
    """Récupère les lignes complètes de la table reference pour les IDs donnés."""
    fmt = ",".join(["%s"] * len(ids))
    cursor.execute(f"SELECT * FROM reference WHERE id IN ({fmt})", tuple(ids))
    return {row["id"]: row for row in cursor.fetchall()}


def transfer_keywords(cursor, from_id: int, to_id: int) -> int:
    """
    Transfère vers to_id les mots-clés de from_id qui n'y sont pas encore.
    Retourne le nombre de lignes insérées.
    """
    cursor.execute(
        "SELECT keyword_id FROM reference_keyword WHERE reference_id = %s",
        (from_id,),
    )
    kw_from = {row["keyword_id"] for row in cursor.fetchall()}
    if not kw_from:
        return 0

    cursor.execute(
        "SELECT keyword_id FROM reference_keyword WHERE reference_id = %s",
        (to_id,),
    )
    kw_to = {row["keyword_id"] for row in cursor.fetchall()}

    to_insert = kw_from - kw_to
    for kw_id in to_insert:
        cursor.execute(
            "INSERT INTO reference_keyword (reference_id, keyword_id) VALUES (%s, %s)",
            (to_id, kw_id),
        )
    return len(to_insert)


def apply_cluster(cursor, keep: dict, delete_refs: list[dict]) -> dict:
    """
    Pour un cluster validé :
      1. Calcule les meilleures valeurs sur l'ensemble keep + deletes.
      2. Met à jour le keep uniquement si au moins un champ change.
      3. Transfère les mots-clés des notices supprimées.
      4. Supprime les notices à supprimer.

    Retourne un dict de statistiques.
    """
    all_refs = [keep] + delete_refs
    updates: list[str] = []
    values:  list      = []

    # --- Disponibilités et fiabilités associées ----------------------------
    for avail_field, reliab_field in AVAILABILITY_PAIRS:
        best = max(all_refs, key=lambda r: r.get(avail_field) or 0)
        best_val   = best.get(avail_field) or 0
        keep_val   = keep.get(avail_field) or 0

        if best_val > keep_val:
            updates += [f"{avail_field} = %s", f"{reliab_field} = %s"]
            values  += [best_val, best.get(reliab_field)]

    # --- Année la plus ancienne -------------------------------------------
    years = [r.get("year") for r in all_refs if r.get("year") is not None]
    if years:
        oldest = min(years, key=lambda y: int(y))
        if int(oldest) < int(keep.get("year") or oldest):
            updates.append("year = %s")
            values.append(oldest)

    # --- Écriture conditionnelle ------------------------------------------
    if updates:
        updates.append("date_modified = NOW()")
        cursor.execute(
            f"UPDATE reference SET {', '.join(updates)} WHERE id = %s",
            values + [keep["id"]],
        )

    # --- Mots-clés et suppressions ----------------------------------------
    total_kw = sum(transfer_keywords(cursor, d["id"], keep["id"]) for d in delete_refs)
    for d in delete_refs:
        cursor.execute("DELETE FROM reference WHERE id = %s", (d["id"],))

    return {
        "deleted":              len(delete_refs),
        "keywords_transferred": total_kw,
        "fields_updated":       updates[:-1] if updates else [],  # sans date_modified
    }


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Applique les fusions de dédoublonnage depuis un fichier JSON."
    )
    parser.add_argument(
        "fichier_json",
        help="Chemin vers le fichier JSON contenant les décisions (keep/delete/skip).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Applique réellement les modifications (sans ce flag : mode DRY RUN).",
    )
    args = parser.parse_args()

    dry_run = not args.apply

    # Chargement du JSON
    try:
        with open(args.fichier_json, "r", encoding="utf-8") as f:
            clusters = json.load(f)
    except FileNotFoundError:
        print(f"Erreur : fichier introuvable → {args.fichier_json}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Erreur : JSON invalide → {e}")
        sys.exit(1)

    mode = "DRY RUN" if dry_run else "APPLY"
    print(f"[{mode}] {len(clusters)} cluster(s) — {args.fichier_json}")

    applied = skipped = warnings = total_deleted = 0

    try:
        conn   = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)

        for cluster in clusters:
            cid = cluster.get("cluster_id") or cluster.get("issn") or "?"

            keep_id, delete_ids, skip = validate_cluster(cluster)

            if skip or (keep_id is not None and not delete_ids):
                skipped += 1
                continue

            if keep_id is None:
                nb_keeps = len([r for r in cluster.get("references", []) if r.get("action") == "keep"])
                print(f"WARNING cluster {cid}: {nb_keeps} 'keep' trouvé(s), attendu 1 — ignoré")
                warnings += 1
                continue

            if dry_run:
                print(f"  cluster {cid}: keep={keep_id}, delete={delete_ids}")
                applied += 1
                continue

            refs_map = fetch_refs(cursor, [keep_id] + delete_ids)

            if keep_id not in refs_map:
                print(f"WARNING cluster {cid}: id {keep_id} introuvable en base — ignoré")
                warnings += 1
                continue

            missing = [d for d in delete_ids if d not in refs_map]
            if missing:
                print(f"WARNING cluster {cid}: ids introuvables ignorés : {missing}")

            delete_refs = [refs_map[d] for d in delete_ids if d in refs_map]
            stats = apply_cluster(cursor, refs_map[keep_id], delete_refs)
            total_deleted += stats["deleted"]
            applied += 1

        if not dry_run:
            conn.commit()

        print(
            f"[{mode}] traités={applied}, ignores={skipped}, "
            f"avertissements={warnings}, supprimes={total_deleted}"
        )

        cursor.close()
        conn.close()

    except MySQLError as err:
        print(f"ERROR MySQL: {err}")
        try:
            conn.rollback()
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()