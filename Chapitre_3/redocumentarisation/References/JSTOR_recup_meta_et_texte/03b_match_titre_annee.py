"""
step2_title_match_year.py
─────────────────────────
Valide les paires (candidate_pairs_year.jsonl) par similarité de titres.

Logique de scoring :
  - Si le titre principal est générique (Introduction, Conclusion, etc.) :
      → seul le titre secondaire (livre/revue) compte, seuil strict 0.85,
        sans bonus de containment.
  - Sinon : moyenne 50/50 titre + titre secondaire (seuil 0.70).

Produit resultats_annee_jstor.json.
"""

import json
import re
import unicodedata

import Levenshtein

INPUT_FILE  = "candidate_pairs_year.jsonl"
OUTPUT_FILE = "resultats_annee_jstor.json"

MIN_SCORE         = 0.70   # seuil normal
MIN_SCORE_GENERIC = 0.85   # seuil strict quand le titre principal est générique

GENERIC_TITLES = {
    "introduction", "conclusion", "preface", "foreword", "afterword",
    "epilogue", "prologue", "bibliography", "index", "appendix",
    "abstract", "summary", "acknowledgements", "acknowledgments",
    "avant propos", "note", "notes", "postface", "postscript",
    "contents", "table of contents", "list of figures", "list of tables",
}


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------
def normalize(t: str) -> str:
    if not t:
        return ""
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^\w\s]", " ", t)
    return " ".join(t.split())


def is_generic(title: str) -> bool:
    return normalize(title) in GENERIC_TITLES


def sim(a: str, b: str, containment: bool = True) -> float:
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return 0.0
    base = Levenshtein.ratio(na, nb)
    if containment:
        shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
        if len(shorter) < len(longer) * 0.6 and shorter in longer:
            ratio = sum(1 for w in shorter.split() if w in longer.split()) / max(len(shorter.split()), 1)
            if ratio >= 0.80:
                return max(base, 0.82)
    return base


# ---------------------------------------------------------------------------
# Score combiné
# ---------------------------------------------------------------------------
def combined_score(pair: dict) -> float | None:
    db_title     = pair["db_title"]
    db_secondary = pair["db_secondary_title"]
    js_title     = pair["jstor_title"]
    js_secondary = pair["jstor_is_part_of"]

    if is_generic(db_title):
        # Titre principal inutilisable : on exige un match strict sur le secondaire
        if not db_secondary or not js_secondary:
            return None
        score = sim(db_secondary, js_secondary, containment=False)
        return score if score >= MIN_SCORE_GENERIC else None

    # Cas normal : moyenne titre + titre secondaire
    s_title     = sim(db_title,     js_title)     if db_title     and js_title     else None
    s_secondary = sim(db_secondary, js_secondary) if db_secondary and js_secondary else None

    if s_title is not None and s_secondary is not None:
        score = (s_title + s_secondary) / 2
    elif s_title is not None:
        score = s_title
    elif s_secondary is not None:
        score = s_secondary
    else:
        return None

    return score if score >= MIN_SCORE else None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    pairs = []
    with open(INPUT_FILE, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                pairs.append(json.loads(line))

    print(f"{len(pairs)} paires candidates à évaluer…")

    best_per_ref: dict[int, dict] = {}

    for pair in pairs:
        score = combined_score(pair)
        if score is None:
            continue

        ref_id = pair["ref_id"]
        if ref_id not in best_per_ref or score > best_per_ref[ref_id]["score"]:
            best_per_ref[ref_id] = {
                "ref_id":             ref_id,
                "year":               pair["year"],
                "db_title":           pair["db_title"],
                "db_secondary_title": pair["db_secondary_title"],
                "trouve":             True,
                "score":              round(score, 4),
                "jstor_item_id":      pair["jstor_item_id"],
                "jstor_title":        pair["jstor_title"],
                "jstor_is_part_of":   pair["jstor_is_part_of"],
                "jstor_url":          pair["jstor_url"],
            }

    all_ref_ids = {p["ref_id"]: p for p in pairs}
    output = []
    for ref_id, first_pair in all_ref_ids.items():
        if ref_id in best_per_ref:
            output.append(best_per_ref[ref_id])
        else:
            output.append({
                "ref_id":             ref_id,
                "year":               first_pair["year"],
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