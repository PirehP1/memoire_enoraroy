#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Généralisation des fusions validées : merge_list.json × corpus_propre.json
→ corrections in-place dans raw_texts/.

Pour chaque document dont les lexical_features contiennent une paire
(token1, token2) de merge_list, le .txt correspondant est corrigé.
Comparaison stricte (casse comprise). Un backup {doc_id}_backup.txt est
créé avant toute modification (jamais écrasé).
applied_corrections.json mémorise les corrections déjà appliquées ; seules les nouvelles paires sont retraitées.

Fichiers générés : rapport_application.txt, applied_corrections.json
"""

import json, re, sys, shutil, pathlib
from collections import defaultdict
from config import CORPUS_JSON, RAW_TEXTS_DIR

try:
    from tqdm import tqdm
except ImportError:
    def tqdm(it, **kw):
        print(f"  {kw.get('desc', '')}..."); return it

SCRIPT_DIR      = pathlib.Path(__file__).resolve().parent
MERGE_LIST_FILE = SCRIPT_DIR / "merge_list.json"
APPLIED_FILE    = SCRIPT_DIR / "applied_corrections.json"
RAPPORT_FILE    = SCRIPT_DIR / "rapport_application.txt"


# ── Utilitaires ───────────────────────────────────────────────────────────────

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

def corr_key(doc_id, t1, t2): return f"{doc_id}|||{t1}|||{t2}"


# ── Dédoublonnage des fusions ─────────────────────────────────────────────────

def build_unique_merges(merge_list):
    """{ (token1, token2): merged } — en cas de conflit, garde le plus fréquent."""
    counts = defaultdict(lambda: defaultdict(int))
    for m in merge_list:
        counts[(m["token1"], m["token2"])][m["merged"]] += 1
    unique = {}
    for (t1, t2), mc in counts.items():
        if len(mc) > 1:
            best = max(mc, key=mc.get)
            print(f"  [CONFLIT] «{t1}»+«{t2}» → {dict(mc)} → on retient «{best}»")
        else:
            best = next(iter(mc))
        unique[(t1, t2)] = best
    return unique


def find_matches_in_corpus(corpus, unique_merges):
    """
    Retourne { doc_id: [{token1, token2, merged, feat_idx}, …] }.
    Comparaison stricte (casse comprise).
    """
    by_t1 = defaultdict(set)
    for (t1, t2) in unique_merges:
        by_t1[t1].add((t1, t2))

    matches = defaultdict(list)
    for item in corpus:
        doc      = item.get("document", {})
        doc_id   = doc.get("doc_id", "")
        features = doc.get("lexical_features", [])
        for i in range(len(features) - 1):
            t1 = features[i].get("token", "")
            t2 = features[i + 1].get("token", "")
            for pair in by_t1.get(t1, set()):
                if pair == (t1, t2):
                    matches[doc_id].append({"token1": t1, "token2": t2,
                                            "merged": unique_merges[pair], "feat_idx": i})
                    break
    return dict(matches)


# ── Correction du .txt ────────────────────────────────────────────────────────

def apply_to_txt(doc_id, token_matches):
    """
    Applique les corrections au fichier {doc_id}.txt.
    Retourne {"found_file", "applied", "not_found_in_text"}.
    """
    txt_path = RAW_TEXTS_DIR / f"{doc_id}.txt"
    result   = {"found_file": False, "applied": [], "not_found_in_text": []}
    if not txt_path.exists():
        return result

    result["found_file"] = True
    text, modified = txt_path.read_text(encoding="utf-8", errors="replace"), False

    for m in token_matches:
        pat = re.compile(rf"{re.escape(m['token1'])}\s*{re.escape(m['token2'])}")
        new_text, n = pat.subn(m["merged"], text)
        if n:
            text, modified = new_text, True
            result["applied"].append({**m, "n_occurrences": n})
        else:
            result["not_found_in_text"].append(m)

    if modified:
        backup = txt_path.with_name(f"{doc_id}_backup.txt")
        if not backup.exists():
            shutil.copy2(txt_path, backup)
        txt_path.write_text(text, encoding="utf-8")

    return result


# ── Main ──────────────────────────────────────────────────────────────────────

def main():

    for p, label in [(CORPUS_JSON, "corpus_propre.json"),
                     (MERGE_LIST_FILE, "merge_list.json"),
                     (RAW_TEXTS_DIR, "raw_texts/")]:
        if not p.exists():
            print(f"\n  [ERREUR] Introuvable : {p}"); sys.exit(1)

    merge_list = load_json_safe(MERGE_LIST_FILE, [])
    if not merge_list:
        print("\n  merge_list.json est vide — rien à faire."); sys.exit(0)

    applied_set = set(load_json_safe(APPLIED_FILE, []))
    unique_merges = build_unique_merges(merge_list)

    print(f"\n  Fusions uniques : {len(unique_merges)}")
    for (t1, t2), merged in sorted(unique_merges.items()):
        print(f"    «{t1}»  +  «{t2}»  →  «{merged}»")

    print(f"\n  Chargement de {CORPUS_JSON.name}…", end=" ", flush=True)
    corpus = json.loads(CORPUS_JSON.read_text(encoding="utf-8"))
    print(f"{len(corpus):,} documents chargés.")

    print("  Recherche des paires dans les lexical_features…", end=" ", flush=True)
    all_matches = find_matches_in_corpus(corpus, unique_merges)
    print(f"{len(all_matches):,} documents concernés.")

    to_process, cnt_deja = {}, 0
    for doc_id, matches in all_matches.items():
        nouvelles = [m for m in matches
                     if corr_key(doc_id, m["token1"], m["token2"]) not in applied_set]
        if nouvelles:
            to_process[doc_id] = nouvelles
        cnt_deja += len(matches) - len(nouvelles)

    print(f"  Déjà appliquées (ignorées)     : {cnt_deja:,}")
    print(f"  Nouvelles corrections          : "
          f"{sum(len(v) for v in to_process.values()):,} dans {len(to_process):,} docs")

    if not to_process:
        print("\n Toutes les corrections sont déjà à jour."); sys.exit(0)

    stats = {"modifie": 0, "fichier_absent": 0, "total_occ": 0, "non_trouve_txt": 0}
    rapport = ["RAPPORT APPLIQUER_DECISIONS", "=" * 65,
               f"Paires uniques : {len(unique_merges)}",
               f"Documents concernés dans le JSON : {len(all_matches)}",
               f"Corrections déjà appliquées (ignorées) : {cnt_deja}", ""]

    for doc_id, token_matches in tqdm(to_process.items(), desc="  Correction .txt", unit="doc"):
        res = apply_to_txt(doc_id, token_matches)

        if not res["found_file"]:
            stats["fichier_absent"] += 1
            rapport.append(f"[ABSENT]   {doc_id}")
            for m in token_matches:
                applied_set.add(corr_key(doc_id, m["token1"], m["token2"]))
            continue

        if res["applied"]:
            n_occ = sum(a["n_occurrences"] for a in res["applied"])
            stats["modifie"]   += 1
            stats["total_occ"] += n_occ
            rapport.append(f"[MODIFIÉ]  {doc_id}  ({len(res['applied'])} paire(s), {n_occ} occ.)")
            for a in res["applied"]:
                rapport.append(f"           «{a['token1']}»+«{a['token2']}» → «{a['merged']}» × {a['n_occurrences']}")
                applied_set.add(corr_key(doc_id, a["token1"], a["token2"]))

        for nf in res["not_found_in_text"]:
            stats["non_trouve_txt"] += 1
            rapport.append(f"  [?txt]   «{nf['token1']}»+«{nf['token2']}» présent JSON, absent .txt")
            applied_set.add(corr_key(doc_id, nf["token1"], nf["token2"]))

        if (stats["modifie"] + stats["fichier_absent"]) % 200 == 0:
            save_json(APPLIED_FILE, list(applied_set))

    save_json(APPLIED_FILE, list(applied_set))

    rapport += ["", "=" * 65, "BILAN",
                f"  .txt modifiés           : {stats['modifie']:,}",
                f"  .txt absents            : {stats['fichier_absent']:,}",
                f"  Occurrences corrigées   : {stats['total_occ']:,}",
                f"  Paires JSON sans .txt   : {stats['non_trouve_txt']:,}",
    RAPPORT_FILE.write_text("\n".join(rapport), encoding="utf-8")

    print(f"     .txt modifiés           : {stats['modifie']:,}")
    print(f"     .txt absents            : {stats['fichier_absent']:,}")
    print(f"     Occurrences corrigées   : {stats['total_occ']:,}")
    if stats["non_trouve_txt"]:
        print(f"     Paires JSON sans .txt   : {stats['non_trouve_txt']:,}  (voir rapport)")
    print(f"     Backups : {{doc_id}}_backup.txt  (même dossier que les .txt)")
    print(f"     Rapport : {RAPPORT_FILE.name}")
    print("\n  Relancez le préprocessing pour arbitrer les cas restants.")


if __name__ == "__main__":
    main()
