#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nettoyage des tokens trop longs (collages OCR : "barbarianscame"…).

Détecte les tokens alpha dépassant un seuil de longueur dans
corpus_propre.json et demande la segmentation correcte à l'utilisateur.
La correction est ensuite appliquée dans le .txt correspondant.

Seuil : THRESHOLD_STRATEGY ("median"|"q3"|"p90"|"p95"|"p99"|"fixed")
        jamais inférieur à THRESHOLD_FLOOR.

Commandes interactives : texte libre (segmentation) | [s] skip token
                         [sk] skip doc | [q] quitter et sauvegarder

Fichiers générés :
  long_tokens_progress.json    — décisions par token (reprise)
  long_tokens_corrections.json — corrections validées
  backups/<timestamp>/         — copies .txt avant modification

Dépendances : pip install tqdm numpy
"""

import json, re, sys, shutil, pathlib
from collections import defaultdict
from datetime import datetime

import numpy as np

try:
    from tqdm import tqdm
except ImportError:
    def tqdm(it, **kw):
        print(f"  {kw.get('desc', '')}..."); return it

from config import CORPUS_JSON as JSON_PATH, RAW_TEXTS_DIR

SCRIPT_DIR       = pathlib.Path(__file__).resolve().parent
PROGRESS_FILE    = SCRIPT_DIR / "long_tokens_progress.json"
CORRECTIONS_FILE = SCRIPT_DIR / "long_tokens_corrections.json"
BACKUP_BASE_DIR  = SCRIPT_DIR / "backups"

THRESHOLD_STRATEGY = "fixed"
THRESHOLD_FIXED    = 20
THRESHOLD_FLOOR    = 15
CONTEXT_WINDOW     = 5
SAVE_EVERY         = 5


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

def make_key(doc_id, i): return f"{doc_id}||{i}"

def get_context_str(features, idx):
    start  = max(0, idx - CONTEXT_WINDOW)
    end    = min(len(features), idx + CONTEXT_WINDOW + 1)
    tokens = [f.get("token", "") for f in features[start:end]]
    rel    = idx - start
    return " ".join(f"[{t}]" if i == rel else t for i, t in enumerate(tokens))


# ── Seuil ─────────────────────────────────────────────────────────────────────

def compute_threshold(corpus):
    print(f"  Calcul du seuil ({THRESHOLD_STRATEGY})...")
    lengths = [
        len(feat.get("token", ""))
        for item in tqdm(corpus, desc="  Distribution")
        for feat in item.get("document", {}).get("lexical_features", [])
        if feat.get("token", "").isalpha()
    ]
    if not lengths:
        return THRESHOLD_FLOOR

    arr = np.array(lengths)
    pct_map = {"median": 50, "q3": 75, "p90": 90, "p95": 95, "p99": 99}
    threshold = (THRESHOLD_FIXED if THRESHOLD_STRATEGY == "fixed"
                 else int(np.percentile(arr, pct_map.get(THRESHOLD_STRATEGY, 95))))
    threshold = max(threshold, THRESHOLD_FLOOR)

    print(f"  Mediane {int(np.median(arr))} | Q3 {int(np.percentile(arr,75))} | "
          f"P90 {int(np.percentile(arr,90))} | P95 {int(np.percentile(arr,95))} | "
          f"P99 {int(np.percentile(arr,99))} | Max {int(arr.max())}")
    print(f"  Seuil retenu ({THRESHOLD_STRATEGY}) : {threshold} caracteres")
    return threshold


# ── Scan ──────────────────────────────────────────────────────────────────────

def scan_long_tokens(corpus, threshold, progress):
    candidates = []
    for doc_idx, item in enumerate(tqdm(corpus, desc="  Scan")):
        doc      = item.get("document", {})
        doc_id   = doc.get("doc_id", "")
        features = doc.get("lexical_features", [])
        for i, feat in enumerate(features):
            token = feat.get("token", "")
            if not token.isalpha() or len(token) <= threshold:
                continue
            key = make_key(doc_id, i)
            if key in progress:
                continue
            candidates.append((doc_idx, doc_id, i, key, token, get_context_str(features, i)))
    return candidates


# ── Application ───────────────────────────────────────────────────────────────

def apply_corrections(doc_corrections, backup_dir):
    applied, not_found = 0, []
    for doc_id, corrs in tqdm(doc_corrections.items(), desc="  Application"):
        txt_path = RAW_TEXTS_DIR / f"{doc_id}.txt"
        if not txt_path.exists():
            not_found.append(doc_id); continue
        shutil.copy2(txt_path, backup_dir / f"{doc_id}.txt")
        text = txt_path.read_text(encoding="utf-8", errors="replace")
        for c in sorted(corrs, key=lambda x: len(x["original"]), reverse=True):
            orig, repl = c["original"], c["replacement"]
            # word-boundary pour eviter les faux positifs sur sous-chaines
            pat = re.compile(rf"(?<![a-zA-ZÀ-ÿ]){re.escape(orig)}(?![a-zA-ZÀ-ÿ])")
            new_text, n = re.subn(pat, repl, text)
            if n:
                text, applied = new_text, applied + 1
            else:
                # fallback sans boundary (contextes OCR atypiques)
                new_text2, n2 = re.subn(re.escape(orig), repl, text)
                if n2:
                    text, applied = new_text2, applied + 1
                else:
                    not_found.append(f"{doc_id}: «{orig}»")
        txt_path.write_text(text, encoding="utf-8")
    return applied, not_found


# ── Main ──────────────────────────────────────────────────────────────────────

def main():

    if not JSON_PATH.exists():
        print(f"\n  [ERREUR] JSON introuvable : {JSON_PATH}"); sys.exit(1)

    SCRIPT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n  Chargement de {JSON_PATH.name}...")
    corpus = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    print(f"  {len(corpus):,} documents.")

    progress    = load_json_safe(PROGRESS_FILE, {})
    corrections = load_json_safe(CORRECTIONS_FILE, [])

    threshold  = compute_threshold(corpus)

    print("\n  Scan des tokens trop longs...")
    candidates = scan_long_tokens(corpus, threshold, progress)
    already    = sum(1 for v in progress.values() if v is not None)
    print(f"  Tokens longs non traites : {len(candidates):,}  |  deja traites : {already:,}")

    if not candidates:
        print("\n  Aucun token long restant a traiter.")
    else:
        print(
            "\n  Saisissez la segmentation correcte (mots separes par espaces)."
            "\n  Commandes : [s] skip token | [sk] skip doc | [q] quitter\n"
        )
        since_save, skip_doc = 0, None

        with tqdm(total=len(candidates), desc="  Arbitrage",
                  unit="token", dynamic_ncols=True) as pbar:

            for doc_idx, doc_id, feat_idx, key, token, context in candidates:

                if doc_id == skip_doc:
                    progress[key] = "skip"
                else:
                    doc   = corpus[doc_idx]["document"]
                    titre = str(doc.get("title", "(sans titre)"))
                    print(f"\n  {'─'*60}")
                    print(f"  Doc    : {doc_id}")
                    print(f"  Titre  : {titre[:80]}{'...' if len(titre) > 80 else ''}")
                    print(f"  Longueur : {len(token)} caracteres  |  Contexte : {context}")
                    print(f"  Token  : «{token}»")

                    while True:
                        ui = input("  Segmentation ([s] skip / [sk] skip doc / [q] quitter) : ").strip()
                        if ui.lower() == "q":
                            save_json(PROGRESS_FILE, progress)
                            save_json(CORRECTIONS_FILE, corrections)
                            print("\n  Progression sauvegardee. Relancez pour continuer.")
                            return
                        if ui.lower() == "s":
                            progress[key] = "skip"; break
                        if ui.lower() == "sk":
                            skip_doc = doc_id; progress[key] = "skip"; break
                        if len(ui) >= 2:
                            progress[key] = "corrected"
                            corrections.append({"doc_id": doc_id, "feat_idx": feat_idx,
                                                "original": token, "replacement": ui})
                            break
                        print("  Saisie invalide. Reessayez ou tapez [s] / [sk].")

                since_save += 1
                if since_save >= SAVE_EVERY:
                    save_json(PROGRESS_FILE, progress)
                    save_json(CORRECTIONS_FILE, corrections)
                    since_save = 0
                pbar.update(1)

        save_json(PROGRESS_FILE, progress)
        save_json(CORRECTIONS_FILE, corrections)
        print("\n  Arbitrage termine pour cette session.")

    n_corr = sum(1 for v in progress.values() if v == "corrected")
    n_skip = sum(1 for v in progress.values() if v == "skip")
    print(f"\n  Corrections validees : {n_corr:,}  |  Conserves : {n_skip:,}")
    print(f"  -> {CORRECTIONS_FILE.name}")

    if not corrections:
        print("\n  Aucune correction a appliquer. Termine."); return

    if input(f"\n  Appliquer les {len(corrections)} corrections aux .txt ? [y/n] : "
             ).lower().strip() != "y":
        print("  Non applique. Relancez et repondez [y]."); return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = BACKUP_BASE_DIR / ts
    backup_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n  Backups -> {backup_dir}")

    doc_corr = defaultdict(list)
    for c in corrections:
        doc_corr[c["doc_id"]].append(c)

    applied, not_found = apply_corrections(doc_corr, backup_dir)

    print("\n" + "=" * 65)
    print(f"  Corrections appliquees : {applied:,}")
    if not_found:
        nf = SCRIPT_DIR / "long_tokens_not_found.txt"
        nf.write_text("\n".join(not_found), encoding="utf-8")
        print(f"  Introuvables           : {len(not_found)}  -> {nf.name}")
    print(f"  Backups -> {backup_dir}")
    print("=" * 65)


if __name__ == "__main__":
    main()
