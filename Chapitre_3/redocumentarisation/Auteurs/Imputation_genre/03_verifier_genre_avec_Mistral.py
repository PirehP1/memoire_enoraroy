"""
Vérification du genre prédit par NamSor via Mistral.
- Accord  → auteurs_genre_verifie_llm.jsonl
- Conflit → conflicts_genre_llm.jsonl
"""

import json, os, re, time
from typing import Optional, Set
from mistralai.client import Mistral

# ── Configuration ──────────────────────────────────────────────────────────────
MISTRAL_API_KEY          = "Y4v09CUm6TRxTsy6h0SV2rYSmgAm02jv"
NAMSOR_RESULTS_FILES     = ["auteurs_genre_impute_vsansnat.jsonl"]
OUTPUT_FILE              = "auteurs_genre_verifie_llm.jsonl"
CONFLICTS_FILE           = "conflicts_genre_llm.jsonl"
DELAY_BETWEEN_REQUESTS   = 2.0
MAX_RETRIES              = 3
NAMSOR_CONFIDENCE_THRESHOLD = 1.0


# ── I/O helpers ────────────────────────────────────────────────────────────────
def append_jsonl(path: str, data: dict) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")


def load_processed_ids() -> Set[str]:
    ids: Set[str] = set()
    for path in (OUTPUT_FILE, CONFLICTS_FILE):
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    ids.add(json.loads(line)["auteur_id"])
                except Exception:
                    pass
    if ids:
        print(f"{len(ids)} auteurs déjà vérifiés — ignorés.")
    return ids


def load_candidates(processed: Set[str]) -> list:
    candidates = []
    for path in NAMSOR_RESULTS_FILES:
        if not os.path.exists(path):
            print(f"Fichier source introuvable : {path}")
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                    if (d.get("traitable") is True
                            and d.get("auteur_id") not in processed
                            and (d.get("probabilite") or 0) <= NAMSOR_CONFIDENCE_THRESHOLD):
                        candidates.append(d)
                except Exception:
                    pass
    return candidates


# ── Appel Mistral ───────────────────────────────────────────────────────────────
def query_mistral(client: Mistral, name: str) -> Optional[str]:
    prompt = (
        f"Détermine le genre probable du prénom dans : '{name}'.\n"
        f"Réponds UNIQUEMENT par 0 (féminin), 1 (masculin) ou 2 (inconnu) :"
    )
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.chat.complete(
                model="mistral-small-latest",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=5,
            )
            raw = resp.choices[0].message.content.strip()
            m = re.search(r"[0-2]", raw)
            return {"0": "female", "1": "male", "2": "unknown"}[m.group()] if m else None
        except Exception as e:
            delay = 5.0 * (2 ** attempt)
            print(f"Erreur Mistral (tentative {attempt+1}/{MAX_RETRIES}) : {e} — pause {delay}s")
            time.sleep(delay)
    return None


# ── Pipeline principal ─────────────────────────────────────────────────────────
def run(client: Mistral) -> None:
    processed  = load_processed_ids()
    candidates = load_candidates(processed)
    total      = len(candidates)
    print(f"{total} auteurs à vérifier.")

    accords = conflits = echecs = 0
    for i, entry in enumerate(candidates, 1):
        aid         = entry["auteur_id"]
        name        = entry["nom_utilise"]
        genre_namsor = entry["genre_identifie"]

        print(f"[{i}/{total}] {name} (NamSor: {genre_namsor}) → ", end="", flush=True)
        genre_llm = query_mistral(client, name)

        if genre_llm is None:
            print("échec API")
            echecs += 1
            continue

        record = {
            "auteur_id":         aid,
            "cle":               entry.get("cle", ""),
            "nom_utilise":       name,
            "genre_namsor":      genre_namsor,
            "probabilite_namsor": entry.get("probabilite"),
            "genre_llm":         genre_llm,
            "source":            "verification_llm_mistral",
        }

        if genre_llm == genre_namsor:
            record["genre_final"] = genre_llm
            append_jsonl(OUTPUT_FILE, record)
            print(f"✅ accord ({genre_llm})")
            accords += 1
        else:
            record["genre_final"] = None
            append_jsonl(CONFLICTS_FILE, record)
            print(f"⚠ conflit (LLM: {genre_llm})")
            conflits += 1

        time.sleep(DELAY_BETWEEN_REQUESTS)

    print(f"\nTerminé — {accords} accords, {conflits} conflits, {echecs} échecs.")


# ── Stats rapides ───────────────────────────────────────────────────────────────
def stats() -> None:
    accords = conflits = 0
    genres: dict = {}
    for path, label in ((OUTPUT_FILE, "accord"), (CONFLICTS_FILE, "conflit")):
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                    if label == "accord":
                        accords += 1
                        g = d.get("genre_final", "unknown")
                        genres[g] = genres.get(g, 0) + 1
                    else:
                        conflits += 1
                except Exception:
                    pass
    total = accords + conflits
    print(f"\n{'─'*40}")
    print(f"Accords  : {accords} ({accords/total*100:.1f}%)" if total else "Aucun résultat.")
    print(f"Conflits : {conflits} ({conflits/total*100:.1f}%)" if total else "")
    for g, n in genres.items():
        print(f"  {g}: {n}")


# ── Entrée ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    client = Mistral(api_key=MISTRAL_API_KEY)
    run(client)
    stats()