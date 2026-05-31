"""
Arbitrage et insertion des genres imputés dans MongoDB.
- Lit auteurs_genre_verifie_llm.jsonl  (accords NamSor + LLM)
- Lit conflicts_genre_llm.jsonl        (conflits ; arbitrage manuel requis)
- Insère le champ genre_impute dans la collection authors.

Arbitrage manuel : ouvrir conflicts_genre_llm.jsonl, remplacer
  "genre_final": null  →  "genre_final": "male" | "female"
  "source": ...        →  "source": "arbitrage_manuel"
Règle stricte : LLM inconnu + pas d'arbitrage → NON inséré.
"""

import json, os
from datetime import datetime
from typing import Dict, List, Tuple
from bson import ObjectId
from pymongo import MongoClient

# ── Configuration ──────────────────────────────────────────────────────────────
MONGO_URI       = "mongodb://localhost:27017"
DB_NAME         = "references_biblio_mongo"
COLLECTION_NAME = "authors"
VERIFIED_FILE   = "auteurs_genre_verifie_llm.jsonl"
CONFLICTS_FILE  = "conflicts_genre_llm.jsonl"


# ── I/O ────────────────────────────────────────────────────────────────────────
def load_jsonl(path: str) -> List[Dict]:
    if not os.path.exists(path):
        print(f"Fichier introuvable : {path}")
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


# ── Mise à jour MongoDB ────────────────────────────────────────────────────────
def build_genre_obj(record: Dict, genre: str, source: str, now: datetime) -> Dict:
    return {
        "valeur":          genre,
        "source":          source,
        "date_imputation": now,
        "methode":         "namsor_llm_verification",
        "details": {
            "namsor_gender":      record.get("genre_namsor") or record.get("genre_identifie"),
            "llm_gender":         record.get("genre_llm"),
            "probabilite_namsor": record.get("probabilite_namsor") or record.get("probabilite"),
            "note":               None,
        },
    }


def update_authors(collection, records: List[Dict],
                   is_conflict: bool = False, dry_run: bool = True) -> Dict:
    stats = {"succes": 0, "erreurs": 0, "sautes": 0}

    for r in records:
        aid          = r.get("auteur_id")
        genre_final  = r.get("genre_final")
        genre_llm    = r.get("genre_llm")

        # Règle stricte : LLM inconnu sans arbitrage manuel → on saute
        if is_conflict and genre_llm == "unknown" and genre_final not in ("male", "female"):
            stats["sautes"] += 1
            continue
        if not aid or genre_final not in ("male", "female"):
            stats["sautes"] += 1
            continue

        source = (r.get("source") if is_conflict and r.get("source") == "arbitrage_manuel"
                  else ("both_agree" if not is_conflict else "conflict_resolved"))

        now = datetime.utcnow()
        update = {
            "$set": {
                "genre_impute":              build_genre_obj(r, genre_final, source, now),
                "info_saisie.date_modified": now,
            }
        }

        if dry_run:
            stats["succes"] += 1
        else:
            try:
                res = collection.update_one({"_id": ObjectId(aid)}, update)
                stats["succes" if res.modified_count else "sautes"] += 1
            except Exception as e:
                print(f"Erreur auteur {aid} : {e}")
                stats["erreurs"] += 1

    return stats


# ── Filtrage des conflits déjà arbitrés manuellement ──────────────────────────
def filter_manually_resolved(conflicts: List[Dict]) -> Tuple[List[Dict], int]:
    resolved = []
    skipped  = 0
    for c in conflicts:
        if c.get("genre_final") in ("male", "female"):
            c["source"] = "arbitrage_manuel"
            resolved.append(c)
        else:
            skipped += 1
    return resolved, skipped


# ── Stats MongoDB ──────────────────────────────────────────────────────────────
def db_stats(collection) -> None:
    print("\n── Distribution en base ──")
    for field in ("genre.valeur", "genre_impute.valeur"):
        print(f"\n{field} :")
        for r in collection.aggregate([{"$group": {"_id": f"${field}", "n": {"$sum": 1}}}]):
            print(f"  {r['_id'] or '—'}: {r['n']}")


# ── Menu & main ────────────────────────────────────────────────────────────────
def main():
    client     = MongoClient(MONGO_URI)
    collection = client[DB_NAME][COLLECTION_NAME]
    accords    = load_jsonl(VERIFIED_FILE)
    conflits   = load_jsonl(CONFLICTS_FILE)

    print(f"Accords : {len(accords)} — Conflits : {len(conflits)}\n")
    print("1. Dry run accords\n2. Insérer accords\n"
          "3. Insérer conflits arbitrés manuellement\n4. Stats MongoDB\n5. Quitter")

    while True:
        choix = input("\nChoix (1-5) : ").strip()

        if choix == "1":
            s = update_authors(collection, accords, dry_run=True)
            print(f"Simulation : {s['succes']} prêts, {s['sautes']} ignorés.")

        elif choix == "2":
            if input(f"Écrire {len(accords)} accords en base ? (oui/non) : ").strip() == "oui":
                s = update_authors(collection, accords, dry_run=False)
                print(f"{s['succes']} insérés, {s['erreurs']} erreurs, {s['sautes']} ignorés.")

        elif choix == "3":
            resolved, skipped = filter_manually_resolved(conflits)
            print(f"{len(resolved)} conflits arbitrés manuellement, {skipped} non résolus ignorés.")
            if resolved and input(f"Insérer ces {len(resolved)} conflits résolus ? (oui/non) : ").strip() == "oui":
                s = update_authors(collection, resolved, is_conflict=True, dry_run=False)
                print(f"{s['succes']} insérés, {s['erreurs']} erreurs, {s['sautes']} ignorés.")

        elif choix == "4":
            db_stats(collection)

        elif choix == "5":
            break

        else:
            print("Choix invalide.")


if __name__ == "__main__":
    main()