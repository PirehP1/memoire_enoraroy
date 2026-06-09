"""
Détection et correction des mots coupés par l'OCR (tirets en fin de token).
v3 — mémoire des paires déjà arbitrées (pair_decisions.json).

Logique :
  1. Règles d'auto-skip (anglo-*, -eenth, ordinaux).
  2. Paire déjà connue → décision appliquée automatiquement.
  3. Nouvelle paire → arbitrage interactif (y/n/q).
  La décision est mémorisée par position (progress.json) ET par paire
  (pair_decisions.json) pour généralisation future.

Fichiers générés dans preprocessing/ :
  progress.json, pair_decisions.json, auto_skipped.json,
  merge_list.json, backups/<timestamp>/
"""

import json, re, sys, shutil, pathlib
from collections import defaultdict, Counter
from datetime import datetime
from config import CORPUS_JSON as JSON_PATH, RAW_TEXTS_DIR

try:
    from tqdm import tqdm
except ImportError:
    print("[INFO] tqdm absent — pip install tqdm pour les barres de progression.")
    def tqdm(it, **kw):
        if kw.get("desc"): print(f"  {kw['desc']}...")
        return it

SCRIPT_DIR          = pathlib.Path(__file__).resolve().parent
PROGRESS_FILE       = SCRIPT_DIR / "progress.json"
MERGE_LIST_FILE     = SCRIPT_DIR / "merge_list.json"
AUTO_SKIPPED_FILE   = SCRIPT_DIR / "auto_skipped.json"
PAIR_DECISIONS_FILE = SCRIPT_DIR / "pair_decisions.json"
BACKUP_BASE_DIR     = SCRIPT_DIR / "backups"

CONTEXT_WINDOW  = 4
SAVE_EVERY      = 5
HYPHEN_CHARS    = r"\-‐‑‒–—⁃"
TOKEN_BROKEN_RE = re.compile(rf"^(.+)[{HYPHEN_CHARS}]$")

ORDINALS = {
    "first","second","third","fourth","fifth","sixth","seventh","eighth",
    "ninth","tenth","eleventh","twelfth","thirteenth","fourteenth","fifteenth",
    "sixteenth","seventeenth","eighteenth","nineteenth","twentieth",
}
ORDINAL_FOLLOWERS = ORDINALS | {"century"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def should_auto_skip(stem: str, token2: str) -> tuple:
    sl, t2l = stem.lower(), token2.lower()
    if sl.endswith("eenth"):  return True, f"radical en -eenth ({stem!r})"
    if sl == "anglo":         return True, f"composé anglo-* ({stem!r}+{token2!r})"
    if sl in ORDINALS and t2l in ORDINAL_FOLLOWERS:
        return True, f"ordinal+suivant ({stem!r}+{token2!r})"
    return False, ""


def load_json_safe(path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"  [AVERT] {path.name} illisible — on repart de zéro.")
    return default


def save_json(path, data):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def pair_key(t1, t2): return f"{t1}|||{t2}"
def make_key(doc_id, idx): return f"{doc_id}||{idx}"
def get_stem(token): m = TOKEN_BROKEN_RE.match(token); return m.group(1) if m else token

def is_next_word(t): return bool(re.match(r"^[a-zA-ZÀ-ÿ]", t))


def get_context_str(features, idx):
    start = max(0, idx - CONTEXT_WINDOW)
    end   = min(len(features), idx + CONTEXT_WINDOW + 2)
    tokens = [f.get("token", "") for f in features[start:end]]
    r1, r2 = idx - start, idx - start + 1
    return " ".join(f"[{t}]" if i in (r1, r2) else t for i, t in enumerate(tokens))


def find_broken_indices(features):
    return [
        i for i, f in enumerate(features[:-1])
        if TOKEN_BROKEN_RE.match(f.get("token", ""))
        and is_next_word(features[i + 1].get("token", ""))
    ]


# ── Initialisation de pair_decisions depuis les sessions précédentes ──────────

def load_pair_decisions(merge_list, progress, data):
    pd = load_json_safe(PAIR_DECISIONS_FILE, {})
    if pd:
        return pd

    print("  Initialisation de pair_decisions.json depuis les sessions précédentes…")
    pd = {pair_key(m["token1"], m["token2"]): "y" for m in merge_list}

    corpus_idx = {item["document"]["doc_id"]: item["document"]
                  for item in data if "doc_id" in item.get("document", {})}

    for key, v in progress.items():
        if v != "n":
            continue
        try:
            doc_id, fi = key.split("||")
            feats = corpus_idx.get(doc_id, {}).get("lexical_features", [])
            fi = int(fi)
            if fi < len(feats) - 1:
                pk = pair_key(feats[fi]["token"], feats[fi + 1]["token"])
                pd.setdefault(pk, "n")
        except (ValueError, IndexError):
            continue

    save_json(PAIR_DECISIONS_FILE, pd)
    y = sum(v == "y" for v in pd.values())
    print(f"    {y:,} paires [y] | {len(pd)-y:,} paires [n] importées.")
    return pd


# ── Application des corrections aux .txt ─────────────────────────────────────

def apply_corrections(doc_merges, backup_dir):
    applied, not_found = 0, []
    for doc_id, merges in tqdm(doc_merges.items(), desc="  Application"):
        txt_path = RAW_TEXTS_DIR / f"{doc_id}.txt"
        if not txt_path.exists():
            print(f"\n  [AVERT] Fichier introuvable : {txt_path.name}")
            not_found.append(doc_id); continue
        shutil.copy2(txt_path, backup_dir / f"{doc_id}.txt")
        text = txt_path.read_text(encoding="utf-8", errors="replace")
        for m in sorted(merges, key=lambda x: x["feat_idx"], reverse=True):
            pat = re.compile(rf"{re.escape(m['token1'])}\s*{re.escape(m['token2'])}", re.IGNORECASE)
            text, n = pat.subn(m["merged"], text)
            if n: applied += 1
            else:
                print(f"\n  [AVERT] Pattern introuvable dans {doc_id} : «{m['token1']}»+«{m['token2']}»")
                not_found.append(f"{doc_id} → {m['token1']}|{m['token2']}")
        txt_path.write_text(text, encoding="utf-8")
    return applied, not_found


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 65)
    print("  PREPROCESSING — MOTS COUPÉS (TIRETS OCR)  v3")
    print("=" * 65)

    if not JSON_PATH.exists():
        print(f"\n  [ERREUR] JSON introuvable : {JSON_PATH}"); sys.exit(1)

    SCRIPT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n  Chargement de {JSON_PATH.name}…")
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"  {len(data):,} documents chargés.")

    progress       = load_json_safe(PROGRESS_FILE, {})
    merge_list     = load_json_safe(MERGE_LIST_FILE, [])
    auto_skipped   = load_json_safe(AUTO_SKIPPED_FILE, [])
    auto_keys      = {e["key"] for e in auto_skipped}
    pair_decisions = load_pair_decisions(merge_list, progress, data)

    # ── Scan ──────────────────────────────────────────────────────────
    print("\n  Scan des mots coupés dans le corpus…")
    to_process = []
    auto_new   = []
    cnt = Counter()   # hum_old, auto_old, pair_y, pair_n

    for doc_idx, item in enumerate(tqdm(data, desc="  Scan")):
        doc      = item.get("document", {})
        doc_id   = doc.get("doc_id", f"doc_{doc_idx}")
        features = doc.get("lexical_features", [])

        for feat_idx in find_broken_indices(features):
            key    = make_key(doc_id, feat_idx)
            token1 = features[feat_idx].get("token", "")
            token2 = features[feat_idx + 1].get("token", "") if feat_idx + 1 < len(features) else ""
            stem   = get_stem(token1)
            pk     = pair_key(token1, token2)

            if key in progress:
                cnt["hum_old"] += 1; continue

            skip, reason = should_auto_skip(stem, token2)
            if skip:
                if key not in auto_keys:
                    auto_new.append({"key": key, "doc_id": doc_id,
                                     "token1": token1, "token2": token2, "reason": reason})
                    auto_keys.add(key)
                else:
                    cnt["auto_old"] += 1
                continue

            if pk in pair_decisions:
                progress[key] = pair_decisions[pk]
                if pair_decisions[pk] == "y":
                    merge_list.append({"doc_id": doc_id, "feat_idx": feat_idx,
                                       "token1": token1, "token2": token2,
                                       "merged": stem + token2})
                    cnt["pair_y"] += 1
                else:
                    cnt["pair_n"] += 1
                continue

            to_process.append((doc_idx, doc_id, feat_idx, key, token1, token2, stem, pk))

    if auto_new:
        auto_skipped.extend(auto_new)
        save_json(AUTO_SKIPPED_FILE, auto_skipped)
    if cnt["pair_y"] + cnt["pair_n"]:
        save_json(PROGRESS_FILE, progress)
        save_json(MERGE_LIST_FILE, merge_list)

    # Déduplication + tri par fréquence décroissante
    pair_freq = Counter(e[-1] for e in to_process)
    seen, to_process_dedup = set(), []
    for entry in to_process:
        if entry[-1] not in seen:
            seen.add(entry[-1]); to_process_dedup.append(entry)
    to_process_dedup.sort(key=lambda e: pair_freq[e[-1]], reverse=True)

    print(f"\n  Décisions précédentes  : {cnt['hum_old']:,} (position) "
          f"| paires connues : {cnt['pair_y']:,} [y] / {cnt['pair_n']:,} [n]")
    print(f"  Auto-ignorés : {cnt['auto_old']:,} connus + {len(auto_new):,} nouveaux")
    print(f"  Occurrences à traiter  : {len(to_process):,}  "
          f"({len(to_process_dedup):,} paires uniques)")

    if auto_new:
        reasons = Counter(e["reason"].split("(")[0].strip() for e in auto_new)
        for cat, n in reasons.most_common():
            ex = [f"«{e['token1']}»+«{e['token2']}»"
                  for e in auto_new if e["reason"].startswith(cat)][:3]
            print(f"    {cat:<35} {n:>4,}×  ex : {', '.join(ex)}")

    # ── Arbitrage interactif ──────────────────────────────────────────
    if to_process_dedup:
        print("\n  Commandes : [y] recoller | [n] laisser | [q] quitter et sauvegarder")
        print("  Chaque décision s'applique à toutes les occurrences identiques.\n")
        since_save = 0

        with tqdm(total=len(to_process_dedup), desc="  Arbitrage",
                  unit="paire", dynamic_ncols=True) as pbar:

            for doc_idx, doc_id, feat_idx, key, token1, token2, stem, pk \
                    in to_process_dedup:

                features = data[doc_idx]["document"].get("lexical_features", [])
                merged   = stem + token2
                titre    = str(data[doc_idx]["document"].get("title", "(sans titre)"))
                freq     = pair_freq[pk]
                freq_msg = (f"{freq} occurrence{'s' if freq > 1 else ''}"
                            + (" — généralisée" if freq > 1 else ""))

                print(f"\n  {'─'*60}")
                print(f"  Fréquence : {freq_msg}")
                print(f"  Doc   : {doc_id}")
                print(f"  Titre : {titre[:80]}{'…' if len(titre) > 80 else ''}")
                print(f"  Contexte : {get_context_str(features, feat_idx)}")
                print(f"  Fusion : «{token1}» + «{token2}»  →  «{merged}»")

                while True:
                    choice = input("  [y] oui / [n] non / [q] quitter : ").lower().strip()
                    if choice in ("y", "n", "q"): break
                    print("  Réponse invalide.")

                if choice == "q":
                    save_json(PROGRESS_FILE, progress)
                    save_json(MERGE_LIST_FILE, merge_list)
                    save_json(PAIR_DECISIONS_FILE, pair_decisions)
                    print("\n  💾 Progression sauvegardée. Relancez pour continuer.")
                    return

                progress[key] = pair_decisions[pk] = choice
                if choice == "y":
                    merge_list.append({"doc_id": doc_id, "feat_idx": feat_idx,
                                       "token1": token1, "token2": token2, "merged": merged})

                since_save += 1
                if since_save >= SAVE_EVERY:
                    save_json(PROGRESS_FILE, progress)
                    save_json(MERGE_LIST_FILE, merge_list)
                    save_json(PAIR_DECISIONS_FILE, pair_decisions)
                    since_save = 0

                pbar.update(1)

        save_json(PROGRESS_FILE, progress)
        save_json(MERGE_LIST_FILE, merge_list)
        save_json(PAIR_DECISIONS_FILE, pair_decisions)
        print("\n Arbitrage terminé.")
    else:
        print("\n Aucun cas à arbitrer.")
        if to_process:
            save_json(PROGRESS_FILE, progress)
            save_json(MERGE_LIST_FILE, merge_list)

    # ── Bilan global ──────────────────────────────────────────────────
    y = sum(1 for v in progress.values() if v == "y")
    n = sum(1 for v in progress.values() if v == "n")
    print(f"\n  Bilan : {y:,} fusions [y] | {n:,} conservés [n] | "
          f"{len(auto_skipped):,} auto-ignorés | {len(pair_decisions):,} paires mémorisées")

    if not merge_list:
        print("  Aucune fusion à appliquer. Terminé."); return

    print(f"\n  Répertoire des textes bruts : {RAW_TEXTS_DIR}")
    if input(f"\n  Appliquer les {len(merge_list)} corrections aux .txt ? [y/n] : "
             ).lower().strip() != "y":
        print("  Corrections non appliquées. Relancez et répondez [y]."); return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = BACKUP_BASE_DIR / ts
    backup_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n  Backups → {backup_dir}")

    doc_merges = defaultdict(list)
    for m in merge_list: doc_merges[m["doc_id"]].append(m)

    print(f"  {len(doc_merges):,} fichiers concernés…")
    applied, not_found = apply_corrections(doc_merges, backup_dir)

    print("\n" + "=" * 65)
    print(f"Corrections appliquées : {applied:,}")
    if not_found:
        report = SCRIPT_DIR / "not_found.txt"
        report.write_text("\n".join(not_found), encoding="utf-8")
        print(f" Introuvables : {len(not_found)} — détails → {report.name}")
    print(f"  Backups → {backup_dir}")
    print(f"\n  Relancez : python 02_lemmatisation.py")
    print("=" * 65)


if __name__ == "__main__":
    main()
