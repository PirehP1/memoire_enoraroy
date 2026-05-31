"""
idref_review_unique.py
──────────────────────
Lit idref_candidates.jsonl et extrait les auteurs pour lesquels
un seul candidat Solr a été trouvé mais qu'aucun match automatique
n'a pu être validé -> comme il n'y a qu'une seule solution dans idref, peut être qu'il s'agit d'eux et ces cas sont plus rapides à vérifier.

Ces cas ambigus sont sauvegardés dans idref_to_review.json avec,
pour chaque auteur :
  - ses titres en base locale
  - les titres IdRef du candidat unique
  - le meilleur score calculé (pour aider l'arbitrage)

Usage :
    python3 idref_review_unique.py
    python3 idref_review_unique.py --input autre_fichier.jsonl
"""

import json
import re
import unicodedata
import argparse
import Levenshtein
from typing import Optional

INPUT_FILE  = "idref_candidates.jsonl"
OUTPUT_FILE = "idref_to_review.json"


def normalize(text: str) -> str:
    if not isinstance(text, str):
        return ""
    text = text.lower()
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("utf-8")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def lev_ratio(a: str, b: str) -> float:
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return 0.0
    if len(na) > 10 and len(nb) > 10 and (na in nb or nb in na):
        return 1.0
    return Levenshtein.ratio(na, nb)


def best_score(local_titles: list[str], idref_works: list[str]) -> tuple[float, str, str]:
    best, bl, bi = 0.0, "", ""
    for lt in local_titles:
        for it in idref_works:
            s = lev_ratio(lt, it)
            if s > best:
                best, bl, bi = s, lt, it
    return best, bl, bi

# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=INPUT_FILE)
    args = parser.parse_args()

    # Compteurs
    total          = 0
    already_matched = 0   # Match automatique trouvé → pas besoin de revue
    zero_candidates = 0   # Aucun candidat Solr → rien à arbitrer
    multi_candidates = 0  # Plusieurs candidats → hors scope de ce script
    to_review_list  = []  # Candidat unique sans match automatique → à arbitrer

    try:
        with open(args.input, encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]
    except FileNotFoundError:
        print(f"[Erreur] Fichier introuvable : {args.input}")
        return

    for line in lines:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        total += 1
        candidates = entry.get("candidates_tried", [])
        match      = entry.get("match")

        if match:
            already_matched += 1
            continue

        n = len(candidates)

        if n == 0:
            zero_candidates += 1
            continue

        if n > 1:
            multi_candidates += 1
            continue

        cand         = candidates[0]
        local_titles = entry.get("local_titles", [])
        idref_works  = cand.get("works", [])

        score, best_local, best_idref = best_score(local_titles, idref_works)

        to_review_list.append({
            "author_id":   entry["author_id"],
            "name":        entry["name"],
            "ppn":         cand["ppn"],
            "label_idref": cand["label"],
            "best_score":  round(score, 4),
            # Titres pour l'arbitrage humain
            "local_titles":  local_titles,
            "idref_works":   idref_works,
            # Meilleure paire pour aider
            "best_pair": {
                "local": best_local,
                "idref": best_idref,
            },
            # Champ à remplir manuellement : true / false / null
            "decision": None,
        })

    to_review_list.sort(key=lambda x: x["best_score"], reverse=True)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(to_review_list, f, ensure_ascii=False, indent=2)

    print(f"Fichier lu          : {args.input}  ({total} entrées)")
    print(f"Matchs automatiques : {already_matched}")
    print(f"Aucun candidat      : {zero_candidates}")
    print(f"Plusieurs candidats : {multi_candidates}  (non inclus ici)")
    print(f"─────────────────────────────────────────")
    print(f"À arbitrer          : {len(to_review_list)}")
    print(f"Fichier de revue    : {OUTPUT_FILE}")


if __name__ == "__main__":
    main()