#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Détection des mots coupés sans tiret — approche dictionnaire (v1).
Mode A : token gauche très court (<= SHORT_MAX_LEN) → toujours signalé.
Mode B : token gauche moyen (SHORT_MAX_LEN < len <= DICT_MAX_LEN) →
         signalé si la concaténation est dans le dictionnaire anglais
         et que les deux fragments ne sont pas tous deux valides seuls.

Les décisions pair_decisions.json (script tiret) et no_hyphen_decisions.json
(sessions précédentes) sont importées.
Chaque décision est mémorisée par paire et généralisée à tout le corpus.
Score OCR par document : nb de problèmes confirmés / nb de tokens.

Fichiers générés :
  no_hyphen_decisions.json, no_hyphen_merge_list.json,
  no_hyphen_doc_scores.json, rapport_no_hyphen.txt

Dépendances : pip install pyspellchecker tqdm
"""

import json, re, sys, pathlib
from collections import defaultdict
from config import CORPUS_JSON

try:
    from spellchecker import SpellChecker
except ImportError:
    print("[ERREUR] pip install pyspellchecker"); sys.exit(1)

try:
    from tqdm import tqdm
except ImportError:
    def tqdm(it, **kw):
        print(f"  {kw.get('desc', '')}..."); return it

SCRIPT_DIR          = pathlib.Path(__file__).resolve().parent
PAIR_DECISIONS_FILE = SCRIPT_DIR / "pair_decisions.json"
NH_DECISIONS_FILE   = SCRIPT_DIR / "no_hyphen_decisions.json"
NH_MERGE_FILE       = SCRIPT_DIR / "no_hyphen_merge_list.json"
NH_DOC_SCORES_FILE  = SCRIPT_DIR / "no_hyphen_doc_scores.json"
RAPPORT_FILE        = SCRIPT_DIR / "rapport_no_hyphen.txt"

CONTEXT_WINDOW = 5
SHORT_MAX_LEN  = 2
DICT_MAX_LEN   = 15
SAVE_EVERY     = 10


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_json_safe(path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            print(f"  [AVERT] {path.name} illisible — on repart de zero.")
    return default

def save_json(path, data):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)

def pair_key(t1, t2):     return f"{t1}|||{t2}"
def is_alpha_only(t):     return bool(t) and t.isalpha()
def is_all_caps(t):       return t.isupper() and len(t) >= 2

def get_context_str(features, idx):
    start  = max(0, idx - CONTEXT_WINDOW)
    end    = min(len(features), idx + CONTEXT_WINDOW + 2)
    tokens = [f.get("token", "") for f in features[start:end]]
    r1, r2 = idx - start, idx - start + 1
    return " ".join(f"[{t}]" if i in (r1, r2) else t for i, t in enumerate(tokens))


# ── Détection ─────────────────────────────────────────────────────────────────

def detect_mode(t1, t2, spell):
    """Retourne 'A', 'B' ou None."""
    if not is_alpha_only(t1) or not is_alpha_only(t2): return None
    if is_all_caps(t1) or is_all_caps(t2):             return None
    l1 = len(t1)
    if l1 <= SHORT_MAX_LEN:
        return "A"
    if SHORT_MAX_LEN < l1 <= DICT_MAX_LEN:
        if t1.lower() in spell and t2.lower() in spell: return None
        if (t1 + t2).lower() in spell:                  return "B"
    return None


def scan_corpus(corpus, spell, known_pairs):
    """Retourne la liste des paires candidates triées par fréquence décroissante."""
    pair_data = {}
    for doc_idx, item in enumerate(tqdm(corpus, desc="  Scan", unit="doc")):
        doc      = item.get("document", {})
        doc_id   = doc.get("doc_id", f"doc_{doc_idx}")
        features = doc.get("lexical_features", [])
        for i in range(len(features) - 1):
            t1 = features[i].get("token", "")
            t2 = features[i + 1].get("token", "")
            mode = detect_mode(t1, t2, spell)
            if mode is None: continue
            pk = pair_key(t1, t2)
            if pk in known_pairs: continue
            if pk not in pair_data:
                pair_data[pk] = {"pk": pk, "t1": t1, "t2": t2, "concat": t1 + t2,
                                 "mode": mode, "freq": 0, "docs": set(),
                                 "exemple_feat_idx": i, "exemple_doc_idx": doc_idx}
            pair_data[pk]["freq"] += 1
            pair_data[pk]["docs"].add(doc_id)

    result = [{**d, "docs": sorted(d["docs"])} for d in pair_data.values()]
    result.sort(key=lambda x: x["freq"], reverse=True)
    return result


# ── Rapport ───────────────────────────────────────────────────────────────────

def write_rapport(nh_decisions, nh_merge_list, doc_scores, corpus):
    total_y = sum(1 for v in nh_decisions.values() if v == "y")
    total_n = sum(1 for v in nh_decisions.values() if v == "n")

    doc_token_count = {i["document"]["doc_id"]: len(i["document"].get("lexical_features", []))
                       for i in corpus}
    doc_titles      = {i["document"]["doc_id"]: i["document"].get("title", "")
                       for i in corpus}

    scored_docs = sorted([
        {"doc_id": did, "titre": str(doc_titles.get(did, ""))[:80],
         "nb_problemes": raw, "nb_tokens": doc_token_count.get(did, 1),
         "score_ocr": round(raw / max(doc_token_count.get(did, 1), 1), 5)}
        for did, raw in doc_scores.items()
    ], key=lambda x: x["score_ocr"], reverse=True)

    sep   = "=" * 65
    lines = [sep, "  RAPPORT — MOTS COUPES SANS TIRET", sep, "",
             f"  Paires [y] recollees    : {total_y:,}",
             f"  Paires [n] conservees   : {total_n:,}",
             f"  Documents affectes      : {len(scored_docs):,}", "",
             "  TOP 30 DOCUMENTS LES PLUS TOUCHES (score = problemes/tokens)",
             "-" * 65,
             f"  {'Score':<8}  {'Prb':>5}  {'Tok':>7}  {'doc_id':<26}  Titre",
             f"  {'-'*8}  {'-'*5}  {'-'*7}  {'-'*26}  {'-'*30}"]
    for d in scored_docs[:30]:
        lines.append(f"  {d['score_ocr']:<8.5f}  {d['nb_problemes']:>5,}  "
                     f"{d['nb_tokens']:>7,}  {d['doc_id']:<26}  {d['titre'][:50]}")
    lines += ["", sep]

    rapport = "\n".join(lines)
    print("\n" + rapport)
    RAPPORT_FILE.write_text(rapport, encoding="utf-8")

    save_json(NH_DOC_SCORES_FILE, {
        d["doc_id"]: {"nb_problemes": d["nb_problemes"], "nb_tokens": d["nb_tokens"],
                      "score_ocr": d["score_ocr"], "titre": d["titre"]}
        for d in scored_docs
    })
    return total_y


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 65)
    print("  DETECTION DES MOTS COUPES SANS TIRET  v1")
    print("=" * 65)

    if not CORPUS_JSON.exists():
        print(f"\n  [ERREUR] Introuvable : {CORPUS_JSON}"); sys.exit(1)

    pair_dec_hyphen = load_json_safe(PAIR_DECISIONS_FILE, {})
    nh_decisions    = load_json_safe(NH_DECISIONS_FILE, {})
    nh_merge_list   = load_json_safe(NH_MERGE_FILE, [])
    doc_scores      = load_json_safe(NH_DOC_SCORES_FILE, {})
    # Normalise doc_scores : accepte les anciens formats {doc_id: dict} ou {doc_id: int}
    doc_scores = {k: (v["nb_problemes"] if isinstance(v, dict) else v)
                  for k, v in doc_scores.items()}

    known_pairs = set(pair_dec_hyphen.keys()) | set(nh_decisions.keys())
    print(f"  Paires connues (tiret) : {len(pair_dec_hyphen):,} | "
          f"(ce script) : {len(nh_decisions):,}")

    print("  Chargement du dictionnaire anglais (pyspellchecker)...", end=" ", flush=True)
    spell = SpellChecker(language="en", distance=0)
    print("OK")

    print(f"  Chargement de {CORPUS_JSON.name}...", end=" ", flush=True)
    corpus = json.loads(CORPUS_JSON.read_text(encoding="utf-8"))
    total_tokens = sum(len(i.get("document", {}).get("lexical_features", [])) for i in corpus)
    print(f"{len(corpus):,} documents, {total_tokens:,} tokens.")

    print(f"\n  Mode A : token gauche <= {SHORT_MAX_LEN} cars | "
          f"Mode B : {SHORT_MAX_LEN+1}-{DICT_MAX_LEN} cars + dictionnaire\n")

    candidates = scan_corpus(corpus, spell, known_pairs)
    to_process = [c for c in candidates if c["pk"] not in nh_decisions]

    # Applique silencieusement les decisions deja connues (scores)
    cnt_auto_y = cnt_auto_n = 0
    for c in candidates:
        if c["pk"] in nh_decisions:
            if nh_decisions[c["pk"]] == "y":
                cnt_auto_y += 1
                for did in c["docs"]:
                    doc_scores[did] = doc_scores.get(did, 0) + c["freq"]
            else:
                cnt_auto_n += 1

    n_a = sum(1 for c in to_process if c["mode"] == "A")
    n_b = sum(1 for c in to_process if c["mode"] == "B")
    print(f"  Candidats total : {len(candidates):,}  |  deja arbitres : [y] {cnt_auto_y}  [n] {cnt_auto_n}")
    print(f"  A arbitrer : {len(to_process):,}  (mode A : {n_a}  |  mode B : {n_b})")

    if not to_process:
        print("\n  Aucun nouveau cas a arbitrer.")
    else:
        print("\n  Commandes : [y] recoller | [n] laisser | [q] quitter\n"
              "  Les paires les plus frequentes sont presentees en premier.\n")
        since_save = 0

        with tqdm(total=len(to_process), desc="  Arbitrage", unit="paire", dynamic_ncols=True) as pbar:
            for c in to_process:
                pk, t1, t2, concat, mode, freq, docs = (
                    c["pk"], c["t1"], c["t2"], c["concat"],
                    c["mode"], c["freq"], c["docs"])
                try:
                    ex_doc      = corpus[c["exemple_doc_idx"]]["document"]
                    context_str = get_context_str(ex_doc.get("lexical_features", []), c["exemple_feat_idx"])
                    titre       = str(ex_doc.get("title", "(sans titre)"))
                    doc_id_ex   = ex_doc.get("doc_id", "?")
                except (IndexError, KeyError):
                    context_str, titre, doc_id_ex = f"{t1} {t2}", "(contexte indisponible)", "?"

                mode_label = (f"fragment court ({len(t1)} car.)" if mode == "A"
                              else f"concat. dictionnaire ({len(t1)}+{len(t2)} cars)")
                freq_msg   = (f"{freq} occurrence{'s' if freq > 1 else ''}"
                              + (f" dans {len(docs)} doc{'s' if len(docs)>1 else ''}"
                                 if len(docs) > 1 else ""))

                print(f"\n  {'─'*62}")
                print(f"  Mode     : {mode_label}  |  Frequence : {freq_msg}")
                print(f"  Doc      : {doc_id_ex}")
                print(f"  Titre    : {titre[:82]}{'...' if len(titre)>82 else ''}")
                print(f"  Contexte : {context_str}")
                print(f"  Propose  : «{t1}» + «{t2}»  ->  «{concat}»")

                while True:
                    choice = input("  [y] oui / [n] non / [q] quitter : ").lower().strip()
                    if choice in ("y", "n", "q"): break
                    print("  Reponse invalide.")

                if choice == "q":
                    save_json(NH_DECISIONS_FILE, nh_decisions)
                    save_json(NH_MERGE_FILE, nh_merge_list)
                    save_json(NH_DOC_SCORES_FILE, doc_scores)
                    print("\n  Progression sauvegardee. Relancez pour continuer.")
                    return

                nh_decisions[pk] = choice
                if choice == "y":
                    nh_merge_list.append({"token1": t1, "token2": t2, "merged": concat,
                                          "mode": mode, "freq": freq, "docs": docs})
                    for did in docs:
                        doc_scores[did] = doc_scores.get(did, 0) + freq

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
        print("\n  Arbitrage termine pour cette session.")

    total_y = write_rapport(nh_decisions, nh_merge_list, doc_scores, corpus)
    print(f"\n  Rapport    -> {RAPPORT_FILE.name}")
    print(f"  Decisions  -> {NH_DECISIONS_FILE.name}")
    print(f"  Fusions    -> {NH_MERGE_FILE.name}")
    print(f"  Scores OCR -> {NH_DOC_SCORES_FILE.name}")
    print(f"\n  Lancez ensuite : python appliquer_no_hyphen.py")
    print(f"  pour appliquer les {total_y} recollages aux fichiers .txt")


if __name__ == "__main__":
    main()
