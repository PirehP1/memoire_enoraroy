#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Détection des mots coupés sans tiret — à appliquer après le premier script de détection des mots coupés sans tirets, puisque
la quantité envisagée est ici plus importante

Principe : un fragment OCR est rare dans le corpus et possède un collocate
quasi-exclusif (le bout manquant). Le PMI sur les bigrammes adjacents
capture ce signal sans dépendre d'un dictionnaire externe.

Algorithme :
  1. Fréquences de tous les tokens alpha du corpus.
  2. Tokens "rares" = frequence <= percentile RARE_PCT.
  3. PMI(t1,t2) = log2[ P(t1,t2) / (P(t1) x P(t2)) ]
  4. Paires retenues : PMI >= PMI_THR, freq_bigram >= MIN_BIGRAM_FREQ,
     len(concat) > max(len(t1), len(t2)), paire inconnue.
  5. Tri par frequence décroissante puis PMI décroissant.
  6. Arbitrage interactif.

Compatibilite : lit pair_decisions.json (script tiret) et
no_hyphen_decisions.json (sessions précédentes).

Fichiers générés :
  no_hyphen_decisions.json, no_hyphen_merge_list.json,
  no_hyphen_doc_scores.json, rapport_no_hyphen.txt

Usage : python 03b_detect_mots_coupes_sans_tirets.py [--rare_pct N] [--pmi_thr F] [--min_freq N]
Dépendances : pip install tqdm numpy
"""

import argparse, json, math, sys, pathlib
from collections import Counter, defaultdict

import numpy as np

try:
    from tqdm import tqdm
except ImportError:
    def tqdm(it, **kw):
        print(f"  {kw.get('desc', '')}..."); return it

from config import CORPUS_JSON

SCRIPT_DIR          = pathlib.Path(__file__).resolve().parent
PAIR_DECISIONS_FILE = SCRIPT_DIR / "pair_decisions.json"
NH_DECISIONS_FILE   = SCRIPT_DIR / "no_hyphen_decisions.json"
NH_MERGE_FILE       = SCRIPT_DIR / "no_hyphen_merge_list.json"
NH_DOC_SCORES_FILE  = SCRIPT_DIR / "no_hyphen_doc_scores.json"
RAPPORT_FILE        = SCRIPT_DIR / "rapport_no_hyphen.txt"

RARE_PCT        = 99.9
PMI_THR         = 20.0
MIN_BIGRAM_FREQ = 4
CONTEXT_WINDOW  = 5
SAVE_EVERY      = 10
MIN_T1_LEN      = 2
MAX_T1_LEN      = 14
MIN_T2_LEN      = 2

EXCLUDE_TOKENS = {
    "a", "an", "the", "of", "in", "to", "and", "or", "as", "at", "by",
    "be", "is", "it", "he", "we", "i", "s",
}


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

def pair_key(t1, t2):  return f"{t1}|||{t2}"
def is_alpha_only(t):  return bool(t) and t.isalpha()
def is_all_caps(t):    return t.isupper() and len(t) >= 2

def get_context_str(features, idx):
    start  = max(0, idx - CONTEXT_WINDOW)
    end    = min(len(features), idx + CONTEXT_WINDOW + 2)
    tokens = [f.get("token", "") for f in features[start:end]]
    r1, r2 = idx - start, idx - start + 1
    return " ".join(f"[{t}]" if i in (r1, r2) else t for i, t in enumerate(tokens))

def norm_doc_score(v):
    """Normalise les anciennes valeurs doc_scores (dict ou int) en int."""
    return v.get("nb_problemes", 0) if isinstance(v, dict) else v


# ── Fréquences et PMI ─────────────────────────────────────────────────────────

def build_frequency_tables(corpus):
    freq_unigram  = Counter()
    freq_bigram   = Counter()
    bigram_docs   = defaultdict(set)
    bigram_example = {}

    for doc_idx, item in enumerate(tqdm(corpus, desc="  Calcul frequences")):
        doc      = item.get("document", {})
        doc_id   = doc.get("doc_id", f"doc_{doc_idx}")
        features = doc.get("lexical_features", [])
        tokens   = [f.get("token", "") for f in features]

        for t in tokens:
            if is_alpha_only(t):
                freq_unigram[t.lower()] += 1

        for i in range(len(tokens) - 1):
            t1, t2 = tokens[i], tokens[i + 1]
            if not is_alpha_only(t1) or not is_alpha_only(t2): continue
            if is_all_caps(t1) or is_all_caps(t2): continue
            k = (t1.lower(), t2.lower())
            freq_bigram[k] += 1
            bigram_docs[k].add(doc_id)
            bigram_example.setdefault(k, (doc_idx, i))

    return freq_unigram, freq_bigram, bigram_docs, bigram_example


def compute_pmi_candidates(freq_unigram, freq_bigram, bigram_docs,
                            bigram_example, rare_threshold, pmi_thr,
                            min_bigram_freq, known_pairs):
    N_uni = sum(freq_unigram.values())
    N_bi  = sum(freq_bigram.values())
    if not N_uni or not N_bi: return []

    candidates = []
    for (t1l, t2l), f_bi in freq_bigram.items():
        pk = pair_key(t1l, t2l)
        if f_bi < min_bigram_freq or pk in known_pairs: continue
        if t1l in EXCLUDE_TOKENS or t2l in EXCLUDE_TOKENS: continue
        if not (MIN_T1_LEN <= len(t1l) <= MAX_T1_LEN) or len(t2l) < MIN_T2_LEN: continue

        f_t1 = freq_unigram.get(t1l, 0)
        if not f_t1 or f_t1 > rare_threshold: continue
        f_t2 = freq_unigram.get(t2l, 0)
        if not f_t2: continue

        pmi = math.log2((f_bi / N_bi) / ((f_t1 / N_uni) * (f_t2 / N_uni)))
        if pmi < pmi_thr: continue

        concat = t1l + t2l
        if len(concat) <= max(len(t1l), len(t2l)): continue

        doc_ex, feat_ex = bigram_example.get((t1l, t2l), (0, 0))
        candidates.append({
            "pk": pk, "t1": t1l, "t2": t2l, "concat": concat,
            "pmi": round(pmi, 3), "freq_bi": f_bi,
            "docs": sorted(bigram_docs[(t1l, t2l)]),
            "ex_doc_idx": doc_ex, "ex_feat_idx": feat_ex,
        })

    candidates.sort(key=lambda x: (-x["freq_bi"], -x["pmi"]))
    return candidates


# ── Main ──────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Detection mots coupes sans tiret — PMI")
    p.add_argument("--rare_pct", type=float, default=RARE_PCT)
    p.add_argument("--pmi_thr",  type=float, default=PMI_THR)
    p.add_argument("--min_freq", type=int,   default=MIN_BIGRAM_FREQ)
    return p.parse_args()


def main():
    args = parse_args()
    print("\n" + "=" * 65)
    print("  DETECTION MOTS COUPES — APPROCHE PMI (v2)")
    print("=" * 65)

    if not CORPUS_JSON.exists():
        print(f"\n  [ERREUR] Introuvable : {CORPUS_JSON}"); sys.exit(1)

    pair_dec_hyphen = load_json_safe(PAIR_DECISIONS_FILE, {})
    nh_decisions    = load_json_safe(NH_DECISIONS_FILE, {})
    nh_merge_list   = load_json_safe(NH_MERGE_FILE, [])
    if not isinstance(nh_merge_list, list): nh_merge_list = []
    # Normalise doc_scores quel que soit le format stocké
    raw_scores = load_json_safe(NH_DOC_SCORES_FILE, {})
    doc_scores = {k: norm_doc_score(v) for k, v in (raw_scores if isinstance(raw_scores, dict) else {}).items()}

    known_pairs = set(pair_dec_hyphen.keys()) | set(nh_decisions.keys())

    corpus = json.loads(CORPUS_JSON.read_text(encoding="utf-8"))
    print(f"  {len(corpus):,} documents charges.")

    freq_unigram, freq_bigram, bigram_docs, bigram_example = build_frequency_tables(corpus)

    all_freqs     = np.array(list(freq_unigram.values()))
    rare_threshold = max(int(np.percentile(all_freqs, args.rare_pct)), 1)

    candidates = compute_pmi_candidates(
        freq_unigram, freq_bigram, bigram_docs, bigram_example,
        rare_threshold, args.pmi_thr, args.min_freq, known_pairs)

    to_process = [c for c in candidates if c["pk"] not in nh_decisions]

    # Applique silencieusement les anciennes decisions [y] sur les scores
    for c in candidates:
        if nh_decisions.get(c["pk"]) == "y":
            for did in c["docs"]:
                doc_scores[did] = doc_scores.get(did, 0) + c["freq_bi"]

    print(f"  Candidats PMI : {len(candidates):,}  |  a arbitrer : {len(to_process):,}")

    if not to_process:
        print("\n  Aucun nouveau cas a arbitrer.")
    else:
        print(f"\n  Commandes : [y] recoller | [n] laisser | [q] quitter\n"
              f"  Tries par frequence decroissante, puis PMI.\n")
        since_save = 0

        with tqdm(total=len(to_process), desc="  Arbitrage", unit="paire") as pbar:
            for c in to_process:
                pk, t1, t2, concat = c["pk"], c["t1"], c["t2"], c["concat"]
                try:
                    ex_doc = corpus[c["ex_doc_idx"]]["document"]
                    ctx    = get_context_str(ex_doc.get("lexical_features", []), c["ex_feat_idx"])
                    titre  = str(ex_doc.get("title", "(sans titre)"))
                except Exception:
                    ctx, titre = f"{t1} {t2}", "?"

                print(f"\n  Freq: {c['freq_bi']} | PMI: {c['pmi']} | «{t1}» + «{t2}» -> «{concat}»")
                print(f"  Titre    : {titre[:80]}{'...' if len(titre) > 80 else ''}")
                print(f"  Contexte : {ctx}")

                while True:
                    choice = input("  [y] oui / [n] non / [q] quitter : ").lower().strip()
                    if choice in ("y", "n", "q"): break

                if choice == "q":
                    save_json(NH_DECISIONS_FILE, nh_decisions)
                    save_json(NH_MERGE_FILE, nh_merge_list)
                    save_json(NH_DOC_SCORES_FILE, doc_scores)
                    print("\n  Progression sauvegardee. Relancez pour continuer.")
                    return

                nh_decisions[pk] = choice
                if choice == "y":
                    nh_merge_list.append({"token1": t1, "token2": t2, "merged": concat,
                                          "freq": c["freq_bi"], "docs": c["docs"]})
                    for did in c["docs"]:
                        doc_scores[did] = doc_scores.get(did, 0) + c["freq_bi"]

                since_save += 1
                if since_save >= SAVE_EVERY:
                    save_json(NH_DECISIONS_FILE, nh_decisions)
                    save_json(NH_MERGE_FILE, nh_merge_list)
                    save_json(NH_DOC_SCORES_FILE, doc_scores)
                    since_save = 0
                pbar.update(1)

        save_json(NH_DECISIONS_FILE, nh_decisions)
        save_json(NH_MERGE_FILE, nh_merge_list)
        save_json(NH_DOC_SCORES_FILE, doc_scores)

    # Rapport final
    doc_token_count = {i["document"]["doc_id"]: len(i["document"].get("lexical_features", []))
                       for i in corpus}
    scored_docs = sorted([
        {"doc_id": did, "nb_problemes": v,
         "score_ocr": v / max(doc_token_count.get(did, 1), 1)}
        for did, v in doc_scores.items()
    ], key=lambda x: x["score_ocr"], reverse=True)

    save_json(NH_DOC_SCORES_FILE, {d["doc_id"]: d for d in scored_docs})
    print(f"\n  Termine. Rapport -> {RAPPORT_FILE.name}")


if __name__ == "__main__":
    main()
