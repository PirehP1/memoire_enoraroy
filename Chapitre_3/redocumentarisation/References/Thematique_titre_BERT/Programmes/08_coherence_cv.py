"""
08_coherence_cv.py — Score de cohérence C_V (gensim) après fusion, hors bruit.

Les topics de bruit éditorial sont exclus du calcul C_V.
Seuls les topics thématiques avec au moins 3 termes présents dans le
dictionnaire gensim sont inclus.

Inputs  : bertopic_model_after_merge/, topics_after_merge.npy,
          docs_ctfidf_cache2.npy, best_n.json
Output  : coherence_after_merge.csv
"""

import json
import numpy as np
import pandas as pd
from bertopic import BERTopic
from gensim.corpora import Dictionary
from gensim.models import CoherenceModel
from config import *

# ── Chargement ────────────────────────────────────────────────────────────────

model        = BERTopic.load(os.path.join(OUTPUT_DIR, "bertopic_model_after_merge"))
topics_after = np.load(os.path.join(OUTPUT_DIR, "topics_after_merge.npy"))
docs_ctfidf  = list(np.load(DOCS_CTFIDF_CACHE, allow_pickle=True))

with open(os.path.join(OUTPUT_DIR, "best_n.json")) as f:
    best_n = json.load(f)["best_n"]
with open(os.path.join(OUTPUT_DIR, "n_after.json")) as f:
    n_after = json.load(f)["n_after"]

topic_counts_r = pd.Series(topics_after).value_counts().sort_index()

# ── Préparation gensim ────────────────────────────────────────────────────────

print("\n=== Cohérence C_V après fusion ===")

tokenized_docs = [doc.lower().split() for doc in docs_ctfidf]
dictionary     = Dictionary(tokenized_docs)

noise_targets = set(MERGE_MAP.values()) & NOISE_TOPIC_IDS if MERGE_MAP else set()
noise_after   = NOISE_TOPIC_IDS | noise_targets | {29} #à changer après réapplication !

print(f"Topics exclus (bruit éditorial) : {sorted(noise_after)}")

topic_lists_after = []
topic_ids_after   = []

for topic_id, terms in model.get_topics().items():
    if topic_id == -1:
        continue
    if topic_id in noise_after:
        continue
    n_docs = topic_counts_r.get(topic_id, 0)
    if n_docs == 0:
        continue
    words = [w for w, _ in terms[:TOP_N_WORDS]]
    words = [w for w in words if w in dictionary.token2id]
    if len(words) >= 3:
        topic_lists_after.append(words)
        topic_ids_after.append(topic_id)

print(f"Topics thématiques utilisables : {len(topic_lists_after)}")
print(f"Topics inclus : {sorted(topic_ids_after)}")

# ── Score C_V ─────────────────────────────────────────────────────────────────

if len(topic_lists_after) == 0:
    coherence_after = float("nan")
    print("  Aucun topic utilisable pour C_V.")
else:
    cm_after = CoherenceModel(
        topics=topic_lists_after,
        texts=tokenized_docs,
        dictionary=dictionary,
        coherence="c_v",
        processes=1,
    )
    coherence_after = cm_after.get_coherence()

print(f"Score C_V après fusion (hors bruit) : {round(coherence_after, 4)}")

pd.DataFrame([{
    "n_topics_avant_fusion":      best_n,
    "n_topics_apres_fusion":      len(topic_lists_after),
    "n_topics_exclus_bruit":      len(noise_after),
    "CV_apres_fusion_hors_bruit": round(coherence_after, 4),
}]).to_csv(os.path.join(OUTPUT_DIR, "coherence_after_merge.csv"), index=False)

print("  → coherence_after_merge.csv")
