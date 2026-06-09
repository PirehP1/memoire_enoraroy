#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Recollage automatique des mots coupés restants.

Fusionne toutes les paires token-tiret + token-suivant non encore
traitées (ni arbitrées, ni auto-skipées). Exclusions :
  • Décisions humaines [y/n] existantes → respectées
  • Auto-skip : ordinaux, anglo-, -eenth, DIRECTION_STEMS
  • SKIP_UPPERCASE_IN_MIDDLE = True → ignore les fusions qui
    produiraient une majuscule au milieu (ex. farCharaxos)

Fichiers générés :
  auto_merge_log.json                 — fusions appliquées (reprise)
  auto_merge_skipped_uppercase.json   — paires ignorées pour majuscule
  backups/<timestamp>/                — copies .txt originales
"""

import json, re, sys, shutil, pathlib
from collections import defaultdict
from datetime import datetime
from config import CORPUS_JSON as JSON_PATH, RAW_TEXTS_DIR

try:
    from tqdm import tqdm
except ImportError:
    def tqdm(it, **kw):
        print(f"  {kw.get('desc', '')}..."); return it

SCRIPT_DIR          = pathlib.Path(__file__).resolve().parent
PROGRESS_FILE       = SCRIPT_DIR / "progress.json"
MERGE_LIST_FILE     = SCRIPT_DIR / "merge_list.json"
AUTO_MERGE_LOG_FILE = SCRIPT_DIR / "auto_merge_log.json"
AUTO_MERGE_UC_FILE  = SCRIPT_DIR / "auto_merge_skipped_uppercase.json"
BACKUP_BASE_DIR     = SCRIPT_DIR / "backups"

SKIP_UPPERCASE_IN_MIDDLE = True

DIRECTION_STEMS = {
    "north", "south", "east", "west",
    "early", "late", "mid", "non", "pre", "post",
}

HYPHEN_CHARS    = r"\-‐‑‒–—⁃"
TOKEN_BROKEN_RE = re.compile(rf"^(.+)[{HYPHEN_CHARS}]$")

ORDINALS = {
    "first","second","third","fourth","fifth","sixth","seventh","eighth",
    "ninth","tenth","eleventh","twelfth","thirteenth","fourteenth","fifteenth",
    "sixteenth","seventeenth","eighteenth","nineteenth","twentieth",
}
ORDINAL_FOLLOWERS = ORDINALS | {"century"}

def load_json_safe(path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return default

def save_json(path, data):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)

def get_stem(t):
    m = TOKEN_BROKEN_RE.match(t); return m.group(1) if m else t

def is_next_word(t): return bool(re.match(r"^[a-zA-ZÀ-ÿ]", t))

def make_key(doc_id, i): return f"{doc_id}||{i}"

def build_pattern(t1, t2):
    return re.compile(rf"{re.escape(t1)}\s*{re.escape(t2)}", re.IGNORECASE)


def should_auto_skip(stem, token2):
    sl, t2l = stem.lower(), token2.lower()
    if sl.endswith("eenth"):                        return True, "eenth"
    if sl == "anglo":                               return True, "anglo"
    if sl in ORDINALS and t2l in ORDINAL_FOLLOWERS: return True, "ordinal"
    if sl in DIRECTION_STEMS:                       return True, "direction/temporel"
    return False, ""


# ── Scan ──────────────────────────────────────────────────────────────────────

def scan(corpus, progress, already_logged, auto_merge_uc_keys):
    """
    Retourne (to_merge, to_skip_uc).
    to_merge   : dicts {key, doc_id, feat_idx, token1, token2, merged}
    to_skip_uc : dicts {key, doc_id, feat_idx, token1, token2}
    """
    handled = set(progress.keys()) | already_logged | auto_merge_uc_keys
    to_merge, to_skip_uc = [], []

    for item in tqdm(corpus, desc="  Scan"):
        doc      = item.get("document", {})
        doc_id   = doc.get("doc_id", "")
        features = doc.get("lexical_features", [])

        for i in range(len(features) - 1):
            t1 = features[i].get("token", "")
            t2 = features[i + 1].get("token", "")
            if not TOKEN_BROKEN_RE.match(t1) or not is_next_word(t2):
                continue
            key = make_key(doc_id, i)
            if key in handled or progress.get(key) == "n":
                continue
            stem = get_stem(t1)
            if should_auto_skip(stem, t2)[0]:
                continue
            merged = stem + t2
            if SKIP_UPPERCASE_IN_MIDDLE and any(c.isupper() for c in merged[1:]):
                to_skip_uc.append({"key": key, "doc_id": doc_id,
                                   "feat_idx": i, "token1": t1, "token2": t2})
            else:
                to_merge.append({"key": key, "doc_id": doc_id,
                                 "feat_idx": i, "token1": t1, "token2": t2,
                                 "merged": merged})

    return to_merge, to_skip_uc


# ── Application ───────────────────────────────────────────────────────────────

def apply_merges(doc_merges, backup_dir):
    applied, not_found = 0, []

    for doc_id, merges in tqdm(doc_merges.items(), desc="  Application"):
        txt_path = RAW_TEXTS_DIR / f"{doc_id}.txt"
        if not txt_path.exists():
            not_found.append(doc_id); continue

        shutil.copy2(txt_path, backup_dir / f"{doc_id}.txt")
        text = txt_path.read_text(encoding="utf-8", errors="replace")

        # Droite → gauche pour éviter les décalages d'index
        for m in sorted(merges, key=lambda x: x["feat_idx"], reverse=True):
            new_text, n = re.subn(
                build_pattern(m["token1"], m["token2"]),
                lambda _, r=m["merged"]: r,   # lambda pour éviter l'interprétation des backslashes
                text,
            )
            if n:
                text, applied = new_text, applied + 1
            else:
                not_found.append(f"{doc_id}: «{m['token1']}»+«{m['token2']}»")

        txt_path.write_text(text, encoding="utf-8")

    return applied, not_found


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"  SKIP_UPPERCASE_IN_MIDDLE = {SKIP_UPPERCASE_IN_MIDDLE}")
    print(f"  DIRECTION_STEMS = {sorted(DIRECTION_STEMS)}")

    if not JSON_PATH.exists():
        print(f"\n  [ERREUR] JSON introuvable : {JSON_PATH}"); sys.exit(1)

    print(f"\n  Chargement de {JSON_PATH.name}…")
    corpus = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    print(f"  {len(corpus):,} documents.")

    progress       = load_json_safe(PROGRESS_FILE, {})
    auto_merge_log = load_json_safe(AUTO_MERGE_LOG_FILE, [])
    auto_merge_uc  = load_json_safe(AUTO_MERGE_UC_FILE, [])
    already_logged = {e["key"] for e in auto_merge_log}
    uc_keys        = {e["key"] for e in auto_merge_uc}

    print("\n  Scan des paires restantes…")
    to_merge, to_skip_uc = scan(corpus, progress, already_logged, uc_keys)

    if to_skip_uc:
        new_uc = [e for e in to_skip_uc if e["key"] not in uc_keys]
        if new_uc:
            save_json(AUTO_MERGE_UC_FILE, auto_merge_uc + new_uc)

    print(f"\n  Paires à fusionner automatiquement : {len(to_merge):,}")
    print(f"  Ignorées (majuscule au milieu)     : {len(to_skip_uc):,}")
    print(f"  Déjà traitées (sessions précéd.)   : {len(already_logged):,}")

    if not to_merge:
        print("\n  Rien à fusionner. Terminé."); return

    print(f"\n  Exemples de fusions à appliquer :")
    for e in to_merge[:10]:
        print(f"    «{e['token1']}» + «{e['token2']}»  →  «{e['merged']}»")
    if len(to_merge) > 10:
        print(f"    … ({len(to_merge) - 10} autres)")

    if SKIP_UPPERCASE_IN_MIDDLE and to_skip_uc:
        print(f"\n  Exemples ignorés (majuscule au milieu) :")
        for e in to_skip_uc[:5]:
            print(f"    «{e['token1']}» + «{e['token2']}»")
        print("  → Pour les traiter : SKIP_UPPERCASE_IN_MIDDLE = False")

    if input(f"\n  Appliquer les {len(to_merge):,} fusions aux .txt ? [y/n] : "
             ).lower().strip() != "y":
        print("  Annulé."); return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = BACKUP_BASE_DIR / ts
    backup_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n  Backups → {backup_dir}")

    doc_merges = defaultdict(list)
    for m in to_merge:
        doc_merges[m["doc_id"]].append(m)

    print(f"  {len(doc_merges):,} fichiers .txt à modifier…")
    applied, not_found = apply_merges(doc_merges, backup_dir)

    auto_merge_log.extend(to_merge)
    save_json(AUTO_MERGE_LOG_FILE, auto_merge_log)

    print("\n" + "=" * 65)
    print(f"  Fusions appliquées  : {applied:,}")
    if not_found:
        nf_path = SCRIPT_DIR / "auto_merge_not_found.txt"
        nf_path.write_text("\n".join(not_found), encoding="utf-8")
        print(f" Introuvables       : {len(not_found)}  → {nf_path.name}")
    print(f"  Journal               → {AUTO_MERGE_LOG_FILE.name}")
    print(f"  Backups               → {backup_dir}")
    print("=" * 65)


if __name__ == "__main__":
    main()
