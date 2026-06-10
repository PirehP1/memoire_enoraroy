
"""
Statistiques des recollages

Lit pair_decisions.json, merge_list.json, auto_skipped.json et
corpus_propre.json pour produire un rapport chiffré sur :
  - le volume de mots coupés détectés dans le corpus
  - la répartition des décisions [y] / [n] / auto-ignorés
  - la distribution fréquentielle des paires (hapax, rares, fréquents)
  - les top 30 paires [y] et [n] les plus fréquentes

Fichiers générés dans stats/ :
  stats_recollages.txt, stats_decisions_y.csv,
  stats_decisions_n.csv, stats_non_arbitres.csv, stats_par_freq.csv

Dépendances : pip install pandas tqdm
"""

import json, re, sys, pathlib
from collections import Counter, defaultdict

import pandas as pd

try:
    from tqdm import tqdm
except ImportError:
    def tqdm(it, **kw):
        print(f"  {kw.get('desc', '')}..."); return it

from config import CORPUS_JSON

SCRIPT_DIR          = pathlib.Path(__file__).resolve().parent
PAIR_DECISIONS_FILE = SCRIPT_DIR / "pair_decisions.json"
MERGE_LIST_FILE     = SCRIPT_DIR / "merge_list.json"
AUTO_SKIPPED_FILE   = SCRIPT_DIR / "auto_skipped.json"
PROGRESS_FILE       = SCRIPT_DIR / "progress.json"
OUT_DIR             = SCRIPT_DIR / "stats"
OUT_DIR.mkdir(exist_ok=True)

HYPHEN_CHARS    = r"\-‐‑‒–—⁃"
TOKEN_BROKEN_RE = re.compile(rf"^(.+)[{HYPHEN_CHARS}]$")
ORDINALS = {
    "first","second","third","fourth","fifth","sixth","seventh","eighth",
    "ninth","tenth","eleventh","twelfth","thirteenth","fourteenth","fifteenth",
    "sixteenth","seventeenth","eighteenth","nineteenth","twentieth",
}
ORDINAL_FOLLOWERS = ORDINALS | {"century"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_json_safe(path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return default

def is_next_word(t):    return bool(re.match(r"^[a-zA-ZÀ-ÿ]", t))
def pair_key(t1, t2):   return f"{t1}|||{t2}"
def get_stem(t):        m = TOKEN_BROKEN_RE.match(t); return m.group(1) if m else t

def should_auto_skip(stem, t2):
    sl, t2l = stem.lower(), t2.lower()
    return sl.endswith("eenth") or sl == "anglo" or (sl in ORDINALS and t2l in ORDINAL_FOLLOWERS)

def freq_bucket(n):
    if n == 1:  return "1 (hapax)"
    if n <= 4:  return "2-4"
    if n <= 9:  return "5-9"
    if n <= 19: return "10-19"
    if n <= 49: return "20-49"
    return "50+"


# ── Scan ──────────────────────────────────────────────────────────────────────

def scan_corpus(corpus):
    """
    Retourne (pair_corpus_freq, pair_doc_count, total_broken, total_auto_skip).
    pair_corpus_freq : Counter { pair_key: nb_occurrences }
    pair_doc_count   : { pair_key: nb_documents_distincts }
    """
    pair_corpus_freq = Counter()
    pair_doc_count   = defaultdict(set)
    total_broken = total_auto_skip = 0

    for item in tqdm(corpus, desc="  Scan corpus"):
        doc      = item.get("document", {})
        doc_id   = doc.get("doc_id", "")
        features = doc.get("lexical_features", [])
        for i in range(len(features) - 1):
            t1 = features[i].get("token", "")
            t2 = features[i + 1].get("token", "")
            if not TOKEN_BROKEN_RE.match(t1) or not is_next_word(t2): continue
            total_broken += 1
            stem = get_stem(t1)
            if should_auto_skip(stem, t2):
                total_auto_skip += 1; continue
            pk = pair_key(t1, t2)
            pair_corpus_freq[pk] += 1
            pair_doc_count[pk].add(doc_id)

    return pair_corpus_freq, {k: len(v) for k, v in pair_doc_count.items()}, total_broken, total_auto_skip


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 65)
    print("  STATISTIQUES DES RECOLLAGES")
    print("=" * 65)

    for p in [CORPUS_JSON, PAIR_DECISIONS_FILE]:
        if not p.exists():
            print(f"\n  [ERREUR] Introuvable : {p}"); sys.exit(1)

    pair_decisions = load_json_safe(PAIR_DECISIONS_FILE, {})
    auto_skipped   = load_json_safe(AUTO_SKIPPED_FILE, [])
    progress       = load_json_safe(PROGRESS_FILE, {})

    decisions_y = {k for k, v in pair_decisions.items() if v == "y"}
    decisions_n = {k for k, v in pair_decisions.items() if v == "n"}

    print(f"  Paires [y] : {len(decisions_y):,}  |  [n] : {len(decisions_n):,}  |  "
          f"auto-ignorees : {len(auto_skipped):,}  |  positions : {len(progress):,}")

    print(f"\n  Chargement de {CORPUS_JSON.name}...", end=" ", flush=True)
    corpus = json.loads(CORPUS_JSON.read_text(encoding="utf-8"))
    total_docs   = len(corpus)
    total_tokens = sum(len(i.get("document", {}).get("lexical_features", [])) for i in corpus)
    print(f"{total_docs:,} documents, {total_tokens:,} tokens.")

    print("\n  Scan de tous les mots coupes dans le corpus...")
    pair_freq, pair_doc_count, total_broken, total_auto_skip = scan_corpus(corpus)
    total_to_arbitrate = sum(pair_freq.values())
    unique_pairs_found = len(pair_freq)

    print(f"  Occurrences brutes : {total_broken:,}  |  auto-ignorees : {total_auto_skip:,}  |  "
          f"a arbitrer : {total_to_arbitrate:,}  |  paires uniques : {unique_pairs_found:,}")

    # Rows par décision
    rows_y, rows_n, rows_pending = [], [], []
    for pk, freq in pair_freq.most_common():
        t1, t2 = pk.split("|||", 1)
        row = {"token1": t1, "token2": t2, "fusion": get_stem(t1) + t2,
               "freq_corpus": freq, "nb_documents": pair_doc_count.get(pk, 0),
               "freq_bucket": freq_bucket(freq)}
        (rows_y if pk in decisions_y else rows_n if pk in decisions_n else rows_pending).append(row)

    df_y, df_n, df_pending = pd.DataFrame(rows_y), pd.DataFrame(rows_n), pd.DataFrame(rows_pending)

    freq_y       = df_y["freq_corpus"].sum()       if not df_y.empty       else 0
    freq_n       = df_n["freq_corpus"].sum()       if not df_n.empty       else 0
    freq_pending = df_pending["freq_corpus"].sum() if not df_pending.empty else 0
    docs_y       = df_y["nb_documents"].sum()       if not df_y.empty       else 0
    docs_n       = df_n["nb_documents"].sum()       if not df_n.empty       else 0
    docs_pending = df_pending["nb_documents"].sum() if not df_pending.empty else 0

    # Distribution fréquentielle
    bucket_order = ["1 (hapax)", "2-4", "5-9", "10-19", "20-49", "50+"]
    def bucket_stats(df, label):
        if df.empty: return pd.DataFrame()
        g = df.groupby("freq_bucket").agg(
            nb_paires=("freq_corpus", "count"),
            total_occurrences=("freq_corpus", "sum")).reset_index()
        g["decision"] = label
        return g

    df_buckets = pd.concat([bucket_stats(df_y, "[y] recolle"),
                             bucket_stats(df_n, "[n] conserve"),
                             bucket_stats(df_pending, "non arbitre")], ignore_index=True)
    if not df_buckets.empty:
        df_buckets["freq_bucket"] = pd.Categorical(df_buckets["freq_bucket"],
                                                    categories=bucket_order, ordered=True)
        df_buckets = df_buckets.sort_values(["freq_bucket", "decision"])

    # Exports CSV
    for df, name in [(df_y, "stats_decisions_y"), (df_n, "stats_decisions_n"),
                     (df_pending, "stats_non_arbitres"), (df_buckets, "stats_par_freq")]:
        if not df.empty:
            df.sort_values("freq_corpus", ascending=False).to_csv(
                OUT_DIR / f"{name}.csv", index=False, encoding="utf-8-sig")

    # Rapport
    pct = lambda n: f"{n / total_to_arbitrate * 100:.1f} %" if total_to_arbitrate else "-%"
    sep, sep2 = "=" * 65, "-" * 65

    lines = [sep, "  RAPPORT STATISTIQUES — RECOLLAGES DE MOTS COUPES (OCR)", sep, "",
             "  1. VOLUME GLOBAL", sep2,
             f"  Documents                          : {total_docs:,}",
             f"  Tokens totaux                      : {total_tokens:,}",
             f"  Occurrences brutes token-tiret     : {total_broken:,}",
             f"  Dont auto-ignorees (regles)        : {total_auto_skip:,}",
             f"  Occurrences soumises a arbitrage   : {total_to_arbitrate:,}",
             f"  -> representent {total_to_arbitrate/total_tokens*100:.2f} % de l'ensemble des tokens"
             if total_tokens else "",
             "", "  2. REPARTITION DES DECISIONS", sep2,
             f"  Paires UNIQUES [y] recollees       : {len(df_y):,}",
             f"  Paires UNIQUES [n] conservees      : {len(df_n):,}",
             f"  Paires UNIQUES non arbitrees       : {len(df_pending):,}",
             f"  {'─'*51}",
             f"  Occurrences [y]                    : {freq_y:,}  ({pct(freq_y)})",
             f"  Occurrences [n]                    : {freq_n:,}  ({pct(freq_n)})",
             f"  Occurrences non arbitrees          : {freq_pending:,}  ({pct(freq_pending)})",
             f"  {'─'*51}",
             f"  Documents touches par [y]          : {docs_y:,}",
             f"  Documents touches par [n]          : {docs_n:,}",
             f"  Documents non arbitres             : {docs_pending:,}",
             "", "  3. DISTRIBUTION FREQUENTIELLE", sep2]

    if not df_buckets.empty:
        lines.append(f"  {'Frequence':<14}  {'Decision':<18}  {'Paires':>7}  {'Occurrences':>12}")
        lines.append(f"  {'-'*14}  {'-'*18}  {'-'*7}  {'-'*12}")
        for _, row in df_buckets.iterrows():
            lines.append(f"  {str(row['freq_bucket']):<14}  {row['decision']:<18}"
                         f"  {int(row['nb_paires']):>7,}  {int(row['total_occurrences']):>12,}")

    hapax = lambda df: len(df[df["freq_corpus"] == 1]) if not df.empty else 0
    hy, hn, hp = hapax(df_y), hapax(df_n), hapax(df_pending)
    lines += ["", "  4. HAPAX (occurrences uniques)", sep2,
              f"  Paires hapax [y]           : {hy:,}",
              f"  Paires hapax [n]           : {hn:,}",
              f"  Paires hapax non arbitrees : {hp:,}",
              f"  Total hapax                : {hy+hn+hp:,}",
              (f"  -> {(hy+hn+hp)/unique_pairs_found*100:.1f} % des paires uniques"
               if unique_pairs_found else "")]

    def top30_rows(df, cols):
        df_s = df.sort_values("freq_corpus", ascending=False).head(30).reset_index(drop=True)
        return [(i+1, row) for i, row in df_s.iterrows()]

    lines += ["", "  5. TOP 30 PAIRES [y] LES PLUS FREQUENTES", sep2,
              f"  {'Rang':<5}  {'token1':<18}  {'token2':<18}  {'fusion':<25}  {'freq':>6}  {'docs':>5}",
              f"  {'-'*5}  {'-'*18}  {'-'*18}  {'-'*25}  {'-'*6}  {'-'*5}"]
    for rank, row in top30_rows(df_y, []):
        lines.append(f"  {rank:<5}  {row['token1']:<18}  {row['token2']:<18}"
                     f"  {row['fusion']:<25}  {int(row['freq_corpus']):>6,}  {int(row['nb_documents']):>5,}")

    lines += ["", "  6. TOP 30 PAIRES [n] LES PLUS FREQUENTES", sep2,
              f"  {'Rang':<5}  {'token1':<18}  {'token2':<18}  {'freq':>6}  {'docs':>5}",
              f"  {'-'*5}  {'-'*18}  {'-'*18}  {'-'*6}  {'-'*5}"]
    for rank, row in top30_rows(df_n, []):
        lines.append(f"  {rank:<5}  {row['token1']:<18}  {row['token2']:<18}"
                     f"  {int(row['freq_corpus']):>6,}  {int(row['nb_documents']):>5,}")

    lines += ["", "  7. PAIRES NON ARBITREES (top 20)", sep2,
              f"  {'Rang':<5}  {'token1':<18}  {'token2':<18}  {'fusion':<25}  {'freq':>6}",
              f"  {'-'*5}  {'-'*18}  {'-'*18}  {'-'*25}  {'-'*6}"]
    for rank, row in top30_rows(df_pending, [])[:20]:
        lines.append(f"  {rank:<5}  {row['token1']:<18}  {row['token2']:<18}"
                     f"  {row['fusion']:<25}  {int(row['freq_corpus']):>6,}")

    lines += ["", sep, f"  Fichiers generes -> {OUT_DIR.resolve()}", sep]

    rapport = "\n".join(lines)
    print("\n" + rapport)
    rapport_path = OUT_DIR / "stats_recollages.txt"
    rapport_path.write_text(rapport, encoding="utf-8")
    print(f"\n  Rapport -> {rapport_path}")
    print(f"  CSV     -> {OUT_DIR}")


if __name__ == "__main__":
    main()
