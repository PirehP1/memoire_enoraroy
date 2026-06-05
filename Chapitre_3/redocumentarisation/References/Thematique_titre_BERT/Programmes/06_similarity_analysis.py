"""
06_similarity_analysis.py — Matrice cosinus, Jaccard, heatmap, paires candidates.

MATRICE DE SIMILARITÉ INTER-TOPICS

  (a) Similarité cosinus entre topic embeddings BERTopic :
      Mesure utilisée en interne par BERTopic (Grootendorst, 2022).
      topic_embeddings_ = vecteurs moyens de chaque cluster dans l'espace 768d.
      Une similarité importante entre deux topics signale qu'ils occupent la même
      région sémantique et sont candidats à la fusion.

  (b) Similarité de Jaccard sur top-20 termes c-TF-IDF :
      Validation secondaire. Cosinus élevé + Jaccard faible = similarité
      superficielle due au vocabulaire générique médiéval.

La heatmap visualise la matrice cosinus et permet d'identifier visuellement
les clusters de bruit.

Inputs  : bertopic_model_before_merge/, topics_before_merge.npy
Outputs : topic_similarity_matrix.csv, topic_similar_pairs.csv,
          topic_jaccard_pairs.csv, topic_similarity_comparison.csv,
          topic_similarity_heatmap.pdf/png, hierarchy_before_merge.html
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from bertopic import BERTopic
from sklearn.metrics.pairwise import cosine_similarity
from config import *

try:
    import seaborn as sns
    HAS_SEABORN = True
except ImportError:
    HAS_SEABORN = False

# ── Chargement ────────────────────────────────────────────────────────────────

model  = BERTopic.load(os.path.join(OUTPUT_DIR, "bertopic_model_before_merge"))
topics = list(np.load(os.path.join(OUTPUT_DIR, "topics_before_merge.npy")))
topic_counts = pd.Series(topics).value_counts().sort_index()

# ── Matrice cosinus ───────────────────────────────────────────────────────────

topic_ids_all    = sorted([t for t in model.get_topics().keys() if t != -1])
topic_embeddings = model.topic_embeddings_
valid_emb        = np.array([topic_embeddings[t] for t in topic_ids_all])

sim_matrix = cosine_similarity(valid_emb)
df_sim = pd.DataFrame(sim_matrix, index=topic_ids_all, columns=topic_ids_all)
df_sim.to_csv(os.path.join(OUTPUT_DIR, "topic_similarity_matrix.csv"))

# ── Heatmap ───────────────────────────────────────────────────────────────────

fig, ax = plt.subplots(figsize=(18, 15))
if HAS_SEABORN:
    sns.heatmap(
        df_sim, ax=ax, cmap="RdYlGn", vmin=0, vmax=1,
        xticklabels=topic_ids_all, yticklabels=topic_ids_all,
        linewidths=0.3, annot=False,
    )
else:
    im = ax.imshow(sim_matrix, cmap="RdYlGn", vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(topic_ids_all)))
    ax.set_yticks(range(len(topic_ids_all)))
    ax.set_xticklabels(topic_ids_all, fontsize=7)
    ax.set_yticklabels(topic_ids_all, fontsize=7)
    plt.colorbar(im, ax=ax)

ax.set_title("Similarité cosinus inter-topics (topic embeddings BERTopic)", fontsize=13)
plt.tight_layout()
fig.savefig(os.path.join(OUTPUT_DIR, "topic_similarity_heatmap.pdf"), dpi=150)
fig.savefig(os.path.join(OUTPUT_DIR, "topic_similarity_heatmap.png"), dpi=150)
plt.close()
print("  Heatmap cosinus sauvegardée.")

# ── Paires candidates à la fusion (cosinus) ───────────────────────────────────
# Hors bruit, hors diagonale.

topic_words = model.get_topics()
pairs = []
for i in range(len(topic_ids_all)):
    for j in range(i + 1, len(topic_ids_all)):
        ti, tj = topic_ids_all[i], topic_ids_all[j]
        if ti in NOISE_TOPIC_IDS or tj in NOISE_TOPIC_IDS:
            continue
        sim = sim_matrix[i, j]
        if sim >= SIMILARITY_THRESHOLD:
            pairs.append({
                "Topic_A":    ti,
                "Topic_B":    tj,
                "Similarity": round(float(sim), 4),
                "N_docs_A":   topic_counts.get(ti, 0),
                "N_docs_B":   topic_counts.get(tj, 0),
                "Terms_A":    " | ".join([w for w, _ in topic_words[ti][:8]]),
                "Terms_B":    " | ".join([w for w, _ in topic_words[tj][:8]]),
            })

df_pairs = (
    pd.DataFrame(pairs)
    .sort_values("Similarity", ascending=False)
    .reset_index(drop=True)
)
df_pairs.to_csv(os.path.join(OUTPUT_DIR, "topic_similar_pairs.csv"), index=False)

print(f"\n  Paires (similarité ≥ {SIMILARITY_THRESHOLD}) :")
print(df_pairs.to_string(index=False))

# ── Hiérarchie avant fusion ───────────────────────────────────────────────────

try:
    model.visualize_hierarchy().write_html(
        os.path.join(OUTPUT_DIR, "hierarchy_before_merge.html")
    )
    print("  Hiérarchie avant fusion sauvegardée.")
except Exception as e:
    print(f"  Hiérarchie HTML impossible : {e}")

# ── Jaccard sur top-20 termes (validation secondaire) ─────────────────────────
# Cosinus élevé + Jaccard faible = similarité superficielle, non fusionné.

print("\n=== Jaccard sur top-20 termes (validation secondaire) ===")
top_words_per_topic = {
    t: set([w for w, _ in topic_words[t][:20]])
    for t in topic_ids_all
    if t in topic_words
}
jaccard_pairs = []
for i in range(len(topic_ids_all)):
    for j in range(i + 1, len(topic_ids_all)):
        ti, tj = topic_ids_all[i], topic_ids_all[j]
        if ti in NOISE_TOPIC_IDS or tj in NOISE_TOPIC_IDS:
            continue
        set_i = top_words_per_topic.get(ti, set())
        set_j = top_words_per_topic.get(tj, set())
        if not set_i or not set_j:
            continue
        intersection = len(set_i & set_j)
        union        = len(set_i | set_j)
        jaccard      = intersection / union if union > 0 else 0
        shared_words = sorted(set_i & set_j)
        if jaccard > 0:
            jaccard_pairs.append({
                "Topic_A":      ti,
                "Topic_B":      tj,
                "Jaccard":      round(jaccard, 4),
                "Cosine":       round(float(sim_matrix[i, j]), 4),
                "Shared_words": " | ".join(shared_words),
                "N_shared":     intersection,
            })

df_jaccard = (
    pd.DataFrame(jaccard_pairs)
    .sort_values("Jaccard", ascending=False)
    .reset_index(drop=True)
)
df_jaccard.to_csv(os.path.join(OUTPUT_DIR, "topic_jaccard_pairs.csv"), index=False)

print("\n  Comparaison Cosine / Jaccard (Jaccard > 0.05) :")
df_compare = df_jaccard[df_jaccard["Jaccard"] > 0.05].copy()
print(df_compare[["Topic_A", "Topic_B", "Cosine", "Jaccard",
                   "Shared_words"]].to_string(index=False))
df_compare.to_csv(
    os.path.join(OUTPUT_DIR, "topic_similarity_comparison.csv"), index=False
)

print("\n  → topic_similarity_matrix.csv")
print("  → topic_similar_pairs.csv")
print("  → topic_jaccard_pairs.csv")
print("  → topic_similarity_comparison.csv")
print("  → topic_similarity_heatmap.pdf/png")
