#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Réparation manuelle ciblée de fichiers .txt (mots collés par OCR).
Utilise wordsegment pour segmenter les tokens trop longs.
Affiche un diff coloré et demande confirmation avant toute écriture.
"""

import pathlib, shutil, re, difflib
from datetime import datetime
from wordsegment import load, segment
from config import RAW_TEXTS_DIR as RAW_DIR

# ── Configuration ─────────────────────────────────────────────────────────────

DOC_IDS = [
    "69825516c835c41957dfa1bb",
    "69825516c835c41957dfa732",
]

BACKUP_DIR          = RAW_DIR / "backups_manual_repair"
LONG_WORD_THRESHOLD = 15


# ── Réparation ────────────────────────────────────────────────────────────────

def smart_repair(text):
    """Segmente uniquement les tokens longs (> LONG_WORD_THRESHOLD), hors URLs."""
    def _fix(m):
        w = m.group(0)
        return " ".join(segment(w)) if len(w) > LONG_WORD_THRESHOLD and "http" not in w else w
    return re.sub(r"[a-zA-Z0-9À-ÿ]{2,}", _fix, text)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("  Chargement de wordsegment...")
    load()

    for doc_id in DOC_IDS:
        path = RAW_DIR / f"{doc_id}.txt"
        print("\n" + "=" * 70)
        print(f"  {doc_id}")
        print("=" * 70)

        if not path.exists():
            print(f"  [ERREUR] Introuvable : {path}"); continue

        original = path.read_text(encoding="utf-8", errors="replace")
        repaired = smart_repair(original)

        diff = list(difflib.ndiff(original.splitlines(), repaired.splitlines()))
        changes = [(l, d) for l, d in enumerate(diff) if d.startswith(("- ", "+ "))]

        if not changes:
            print("  Aucun mot colle detecte."); continue

        print("\n  Modifications identifiees :")
        for _, d in changes:
            color = "\033[91m" if d.startswith("- ") else "\033[92m"
            label = "AVANT" if d.startswith("- ") else "APRES"
            print(f"  {color}{label}: {d[2:].strip()}\033[0m")
            if d.startswith("+ "):
                print("  " + "-" * 40)

        choice = input(f"\n  Appliquer sur {doc_id}.txt ? [y/n] : ").lower().strip()
        if choice == "y":
            BACKUP_DIR.mkdir(exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            shutil.copy2(path, BACKUP_DIR / f"{doc_id}_{ts}.txt.bak")
            path.write_text(repaired, encoding="utf-8")
            print(f"  Applique. Backup -> {BACKUP_DIR.name}/")
        else:
            print("  Ignore.")

    print("\n  Termine.")


if __name__ == "__main__":
    main()
