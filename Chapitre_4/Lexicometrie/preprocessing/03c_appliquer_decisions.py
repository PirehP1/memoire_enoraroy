"""
Application des fusions sans tiret aux .txt

Lit no_hyphen_merge_list.json et applique chaque
recollage dans les fichiers .txt, avec backup horodaté et rapport de stats.
Idempotent : no_hyphen_applied_log.json mémorise les fusions déjà traitées.

Fichiers générés :
  no_hyphen_applied_log.json, stats/stats_no_hyphen_applied.txt,
  backups/<timestamp>/
"""

import json, re, shutil, sys, pathlib
from collections import defaultdict
from datetime import datetime
from config import RAW_TEXTS_DIR

try:
    from tqdm import tqdm
except ImportError:
    def tqdm(it, **kw):
        print(f"  {kw.get('desc', '')}..."); return it

SCRIPT_DIR    = pathlib.Path(__file__).resolve().parent
NH_MERGE_FILE = SCRIPT_DIR / "no_hyphen_merge_list.json"
APPLIED_LOG   = SCRIPT_DIR / "no_hyphen_applied_log.json"
BACKUP_DIR    = SCRIPT_DIR / "backups"
STATS_FILE    = SCRIPT_DIR / "stats" / "stats_no_hyphen_applied.txt"
STATS_FILE.parent.mkdir(exist_ok=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

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

def build_pattern(t1, t2):
    """Regex avec word-boundary : t1 + espaces optionnels + t2."""
    return re.compile(rf"(?<![a-zA-ZÀ-ÿ]){re.escape(t1)}\s*{re.escape(t2)}(?![a-zA-ZÀ-ÿ])")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 65)
    print("  01h — APPLICATION DES RECOLLAGES SANS TIRET")
    print("=" * 65)

    if not NH_MERGE_FILE.exists():
        print(f"\n  [ERREUR] {NH_MERGE_FILE.name} introuvable.")
        print("  Lancez d'abord : python 01f_detection_no_hyphen_dict.py")
        sys.exit(1)

    merge_list   = load_json_safe(NH_MERGE_FILE, [])
    applied_log  = load_json_safe(APPLIED_LOG, [])
    already_done = {f"{e['token1']}|||{e['token2']}" for e in applied_log}
    to_apply     = [m for m in merge_list
                    if f"{m['token1']}|||{m['token2']}" not in already_done]

    print(f"\n  Fusions dans la liste     : {len(merge_list):,}")
    print(f"  Deja appliquees (log)     : {len(already_done):,}")
    print(f"  A appliquer cette session : {len(to_apply):,}")

    if not to_apply:
        print("\n  Tout est deja applique. Termine."); return

    print(f"\n  Exemples :")
    for m in to_apply[:8]:
        print(f"    «{m['token1']}» + «{m['token2']}»  ->  «{m['merged']}»"
              f"  (freq={m['freq']}, {len(m['docs'])} doc{'s' if len(m['docs'])>1 else ''})")
    if len(to_apply) > 8:
        print(f"    ... ({len(to_apply) - 8} autres)")

    if input(f"\n  Appliquer ces {len(to_apply)} fusions aux .txt ? [y/n] : "
             ).strip().lower() != "y":
        print("  Annule."); return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = BACKUP_DIR / ts
    backup_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n  Backups -> {backup_dir}")

    doc_to_merges = defaultdict(list)
    for m in to_apply:
        for doc_id in m["docs"]:
            doc_to_merges[doc_id].append(m)

    print(f"  {len(doc_to_merges):,} fichiers .txt a modifier...\n")

    applied_total, not_found_list, doc_stats = 0, [], {}

    for doc_id, merges in tqdm(doc_to_merges.items(), desc="  Application"):
        txt_path = RAW_TEXTS_DIR / f"{doc_id}.txt"
        if not txt_path.exists():
            not_found_list.append(f"FICHIER ABSENT : {doc_id}"); continue

        shutil.copy2(txt_path, backup_dir / f"{doc_id}.txt")
        text = txt_path.read_text(encoding="utf-8", errors="replace")
        doc_applied = doc_missing = 0

        for m in sorted(merges, key=lambda x: len(x["token1"]), reverse=True):
            new_text, n = re.subn(build_pattern(m["token1"], m["token2"]), m["merged"], text)
            if n:
                text, applied_total, doc_applied = new_text, applied_total + n, doc_applied + n
            else:
                # Fallback sans word-boundary
                new_text2, n2 = re.subn(
                    re.compile(rf"{re.escape(m['token1'])}\s*{re.escape(m['token2'])}"),
                    m["merged"], text)
                if n2:
                    text, applied_total, doc_applied = new_text2, applied_total + n2, doc_applied + n2
                else:
                    not_found_list.append(f"{doc_id}: «{m['token1']}»+«{m['token2']}»")
                    doc_missing += 1

        txt_path.write_text(text, encoding="utf-8")
        doc_stats[doc_id] = {"applied": doc_applied, "not_found": doc_missing}

    applied_log.extend(to_apply)
    save_json(APPLIED_LOG, applied_log)

    # Rapport
    sep   = "=" * 65
    lines = [sep, "  RAPPORT — APPLICATION DES RECOLLAGES SANS TIRET", sep, "",
             f"  Fusions demandees       : {len(to_apply):,}",
             f"  Remplacements effectues : {applied_total:,}",
             f"  Patterns introuvables   : {len(not_found_list):,}",
             f"  Fichiers modifies       : {len(doc_to_merges):,}",
             f"  Backup                  : {backup_dir}", "",
             "  TOP 20 DOCUMENTS PAR NB DE CORRECTIONS", "-" * 65,
             f"  {'doc_id':<26}  {'Appliquees':>10}  {'Introuvables':>12}",
             f"  {'-'*26}  {'-'*10}  {'-'*12}"]
    for doc_id, s in sorted(doc_stats.items(), key=lambda x: x[1]["applied"], reverse=True)[:20]:
        lines.append(f"  {doc_id:<26}  {s['applied']:>10,}  {s['not_found']:>12,}")
    if not_found_list:
        lines += ["", "  PATTERNS INTROUVABLES (premiers 30)", "-" * 65]
        lines += [f"  {x}" for x in not_found_list[:30]]
    lines += ["", sep]

    rapport = "\n".join(lines)
    print("\n" + rapport)
    STATS_FILE.write_text(rapport, encoding="utf-8")

    print(f"\n  Corrections appliquees : {applied_total:,}")
    print(f"  Rapport -> {STATS_FILE}")
    print(f"  Log     -> {APPLIED_LOG.name}")
    if not_found_list:
        nf = SCRIPT_DIR / "no_hyphen_not_found.txt"
        nf.write_text("\n".join(not_found_list), encoding="utf-8")
        print(f"  Introuvables -> {nf.name}")


if __name__ == "__main__":
    main()
