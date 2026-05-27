"""
step2_title_match.py
────────────────────
Lit candidate_pairs.jsonl (produit par step1) et valide chaque paire
par comparaison de titres (SequenceMatcher).

Produit resultats_isbn_jstor.json :
  [
    {
      "ref_id":          123,
      "db_issn":         "0084-3067",
      "db_title":        "…",
      "trouve":          true,
      "score":           0.91,
      "jstor_item_id":   "…",
      "jstor_url":       "…"
    },
    …
  ]
"""

import json
import re
import Levenshtein

INPUT_FILE  = "candidate_pairs.jsonl"
OUTPUT_FILE = "resultats_isbn_jstor.json"

# Seuils de validation
MIN_CHAPTER_SIM = 0.80
MIN_BOOK_SIM    = 0.70


# ---------------------------------------------------------------------------
# Comparaison de titres
# ---------------------------------------------------------------------------
def normalize_title(t: str) -> str:
    if not t:
        return ""
    t = t.lower()
    t = re.sub(r"[^\w\s]", " ", t)   # ponctuation → espace
    return " ".join(t.split())


def title_sim(a: str, b: str) -> float:
    """Similarité avec bonus si l'un est contenu dans l'autre."""
    na, nb = normalize_title(a), normalize_title(b)
    if not na or not nb:
        return 0.0

    base = Levenshtein.ratio(na, nb)

    # Bonus containment : utile pour les titres tronqués
    shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
    if len(shorter) < len(longer) * 0.6 and shorter in longer:
        words_s = shorter.split()
        words_l = longer.split()
        ratio   = sum(1 for w in words_s if w in words_l) / max(len(words_s), 1)
        if ratio >= 0.80:
            return max(base, 0.82)

    return base


def best_config_score(db_title: str, db_secondary: str,
                       jstor_title: str, jstor_is_part_of: str) -> float | None:
    """
    Teste les 4 configurations (chapitre/livre peuvent être dans des champs
    inversés selon la source) et retourne le meilleur score, ou None si aucun
    ne passe les seuils.
    """
    configs = [
        (db_title,     db_secondary, jstor_title,        jstor_is_part_of),
        (db_title,     db_secondary, jstor_is_part_of,   jstor_title),
        (db_secondary, db_title,     jstor_title,        jstor_is_part_of),
        (db_secondary, db_title,     jstor_is_part_of,   jstor_title),
    ]

    best = None
    for wc_chap, wc_book, js_chap, js_book in configs:
        if not wc_chap or not js_chap:
            continue
        chap = title_sim(wc_chap, js_chap)
        if chap < MIN_CHAPTER_SIM:
            continue
        book = title_sim(wc_book, js_book) if wc_book and js_book else None
        if book is not None and book < MIN_BOOK_SIM:
            continue
        score = chap * 0.7 + (book or chap) * 0.3
        if best is None or score > best:
            best = score

    return best


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    # Lire toutes les paires candidates
    pairs = []
    with open(INPUT_FILE, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                pairs.append(json.loads(line))

    print(f"{len(pairs)} paires candidates à évaluer…")

    # Pour chaque ref_id, on garde le meilleur match (score le plus élevé)
    best_per_ref: dict[int, dict] = {}

    for pair in pairs:
        score = best_config_score(
            pair["db_title"],
            pair["db_secondary_title"],
            pair["jstor_title"],
            pair["jstor_is_part_of"],
        )
        if score is None:
            continue

        ref_id = pair["ref_id"]
        if ref_id not in best_per_ref or score > best_per_ref[ref_id]["score"]:
            best_per_ref[ref_id] = {
                "ref_id":               ref_id,
                "db_issn":              pair["db_issn"],
                "db_title":             pair["db_title"],
                "db_secondary_title":   pair["db_secondary_title"],
                "trouve":               True,
                "score":                round(score, 4),
                "jstor_item_id":        pair["jstor_item_id"],
                "jstor_title":          pair["jstor_title"],
                "jstor_is_part_of":     pair["jstor_is_part_of"],
                "jstor_url":            pair["jstor_url"],
            }

    # Récupérer tous les ref_id candidats pour signaler les non-trouvés
    all_ref_ids = {p["ref_id"]: p for p in pairs}
    output = []
    for ref_id, first_pair in all_ref_ids.items():
        if ref_id in best_per_ref:
            output.append(best_per_ref[ref_id])
        else:
            output.append({
                "ref_id":             ref_id,
                "db_issn":            first_pair["db_issn"],
                "db_title":           first_pair["db_title"],
                "db_secondary_title": first_pair["db_secondary_title"],
                "trouve":             False,
                "score":              None,
                "jstor_item_id":      None,
                "jstor_title":        None,
                "jstor_is_part_of":   None,
                "jstor_url":          None,
            })

    output.sort(key=lambda r: (not r["trouve"], r["ref_id"]))

    with open(OUTPUT_FILE, "w", encoding="utf-8") as fh:
        json.dump(output, fh, ensure_ascii=False, indent=2)

    found = sum(1 for r in output if r["trouve"])
    print(f"\nRésultats : {found}/{len(output)} trouvés ({100*found/len(output):.1f} %)")
    print(f"Fichier de sortie : {OUTPUT_FILE}")


if __name__ == "__main__":
    main()