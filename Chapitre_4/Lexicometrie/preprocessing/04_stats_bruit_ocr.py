"""
Audit rapide de l'avancement du nettoyage des tokens longs (OCR).

Compare trois ensembles :
  1. Documents suspects  — contiennent au moins un token > THRESHOLD
                           (détecté directement dans corpus_propre.json)
  2. Documents audites   — au moins un token vu/arbitre dans
                           long_tokens_progress.json
  3. Documents modifies  — fichier backup present dans BACKUP_DIR
                           (réparation effective confirmée)

Affiche la liste des IDs restant a auditer, formatee pour copier-coller
dans DOC_IDS de 02b_correction_ocr_ciblee.py.
"""

import json, re, pathlib
from config import CORPUS_JSON as JSON_PATH, RAW_TEXTS_DIR

SCRIPT_DIR    = pathlib.Path(__file__).resolve().parent
PROGRESS_FILE = SCRIPT_DIR / "long_tokens_progress.json"
BACKUP_DIR    = RAW_TEXTS_DIR / "backups_manual_repair"
THRESHOLD     = 20


def main():
    # 1. Documents suspects (tokens longs dans le corpus JSON)
    suspect_ids = set()
    if JSON_PATH.exists():
        corpus  = json.loads(JSON_PATH.read_text(encoding="utf-8"))
        pattern = re.compile(r"\b[a-zA-ZÀ-ÿ0-9]{" + str(THRESHOLD + 1) + r",}\b")
        for item in corpus:
            doc_id   = item.get("document", {}).get("doc_id", "")
            features = item.get("document", {}).get("lexical_features", [])
            tokens   = [f.get("token", "") for f in features]
            found    = [w for w in pattern.findall(" ".join(tokens))
                        if not any(x in w.lower() for x in ("http", "www", "doi"))]
            if found:
                suspect_ids.add(doc_id)

    # 2. Documents audites (vus dans long_tokens_progress.json)
    audited_ids = set()
    if PROGRESS_FILE.exists():
        progress    = json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
        audited_ids = {k.split("||")[0] for k in progress}

    # 3. Documents effectivement modifies (backup present)
    modified_ids = set()
    if BACKUP_DIR.exists():
        for f in BACKUP_DIR.glob("*.bak"):
            modified_ids.add(f.name.split("_")[0])

    remaining = sorted(suspect_ids - audited_ids)
    print("  AUDIT OCR — TOKENS LONGS")
    print(f"  Suspects (tokens > {THRESHOLD})   : {len(suspect_ids)}")
    print(f"  Audites (vus/arbitres)        : {len(audited_ids)}")
    print(f"  Modifies (reparations reelles): {len(modified_ids)}")
    print(f"  Reste a auditer               : {len(remaining)}")

    if remaining:
        print("\n  IDs restants (format DOC_IDS) :")
        for r in remaining:
            print(f'    "{r}",')


if __name__ == "__main__":
    main()
