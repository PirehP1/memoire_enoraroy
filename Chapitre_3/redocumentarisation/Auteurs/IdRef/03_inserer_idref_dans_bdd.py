"""
idref_update_db.py
──────────────────
Met à jour la colonne ppn_idref dans MySQL à partir de deux sources possibles :

  1. idref_candidates.jsonl  (matchs automatiques d'idref_fetch.py)
       → entrées avec un champ "match" non null

  2. idref_to_review.json    (arbitrage manuel d'idref_review_unique.py)
       → entrées avec "decision": true

Usage :
    python3 idref_update_db.py                              # aperçu depuis idref_candidates.jsonl
    python3 idref_update_db.py --input idref_to_review.json # aperçu depuis le fichier de revue
    python3 idref_update_db.py --commit                     # applique les mises à jour
"""

import json
import argparse
import mysql.connector

MYSQL_CONFIG = {
    "host":     "localhost",
    "user":     "root",
    "password": "PASSWORD",
    "database": "DATABASE",
}

DEFAULT_INPUT = "idref_candidates.jsonl"


def load_from_candidates(path: str) -> list[dict]:
    """Charge les matchs automatiques depuis idref_candidates.jsonl."""
    matches = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get("match"):
                        matches.append({
                            "author_id": entry["author_id"],
                            "name":      entry["name"],
                            "ppn":       entry["match"]["ppn"],
                            "score":     entry["match"]["score"],
                            "note":      f"auto  local={entry['match']['matched_local']!r}  "
                                         f"idref={entry['match']['matched_idref']!r}",
                        })
                except Exception:
                    pass
    except FileNotFoundError:
        print(f"[Erreur] Fichier introuvable : {path}")
    return matches


def load_from_review(path: str) -> list[dict]:
    """Charge les décisions manuelles (decision=true) depuis idref_to_review.json."""
    matches = []
    try:
        with open(path, encoding="utf-8") as f:
            entries = json.load(f)
        for entry in entries:
            if entry.get("decision") is True:
                matches.append({
                    "author_id": entry["author_id"],
                    "name":      entry["name"],
                    "ppn":       entry["ppn"],
                    "score":     entry.get("best_score", 0),
                    "note":      "décision manuelle",
                })
    except FileNotFoundError:
        print(f"[Erreur] Fichier introuvable : {path}")
    except json.JSONDecodeError as e:
        print(f"[Erreur] JSON invalide : {e}")
    return matches


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",  default=DEFAULT_INPUT,
                        help="Fichier source (.jsonl auto ou .json revue)")
    parser.add_argument("--commit", action="store_true",
                        help="Applique les UPDATE (sans ce flag : aperçu seul)")
    args = parser.parse_args()

    # Détection automatique du format selon l'extension
    if args.input.endswith(".json") and not args.input.endswith(".jsonl"):
        matches = load_from_review(args.input)
        source  = "revue manuelle"
    else:
        matches = load_from_candidates(args.input)
        source  = "matchs automatiques"

    if not matches:
        print("Aucune entrée à mettre à jour.")
        return

    print(f"Source : {args.input}  ({source})")
    print(f"{len(matches)} auteur(s) à mettre à jour :\n")
    for m in matches:
        print(f"  [{m['author_id']}] {m['name']}")
        print(f"      ppn_idref = {m['ppn']}  score={m['score']:.3f}  ({m['note']})")

    if not args.commit:
        print("\nMode aperçu — aucune modification.")
        print("Relancez avec --commit pour appliquer.")
        return

    try:
        conn    = mysql.connector.connect(**MYSQL_CONFIG)
        cur     = conn.cursor()
        updated = 0
        for m in matches:
            cur.execute("""
                UPDATE auteur
                SET ppn_idref = %s
                WHERE id = %s
                  AND (ppn_idref IS NULL OR ppn_idref = '')
            """, (m["ppn"], m["author_id"]))
            updated += cur.rowcount
        conn.commit()
        cur.close()
        conn.close()
        print(f"\n✅ {updated} ligne(s) mise(s) à jour dans la table `auteur`.")
    except mysql.connector.Error as e:
        print(f"[DB] Erreur : {e}")


if __name__ == "__main__":
    main()