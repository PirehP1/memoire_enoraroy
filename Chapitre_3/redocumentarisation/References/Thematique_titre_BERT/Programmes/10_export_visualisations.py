"""
10_export_visualisations.py — Barchart, hiérarchie et sauvegarde modèle final.

Tentative de sauvegarde en PDF (nécessite kaleido).
Fallback HTML si kaleido n'est pas disponible.

Inputs  : bertopic_model_after_merge/, n_after.json
Outputs : barchart_final.pdf/html, hierarchy_final.pdf/html,
          bertopic_ward_model_final/
"""

import json
from bertopic import BERTopic
from config import *

# ── Chargement ────────────────────────────────────────────────────────────────

model = BERTopic.load(os.path.join(OUTPUT_DIR, "bertopic_model_after_merge"))

with open(os.path.join(OUTPUT_DIR, "n_after.json")) as f:
    n_after = json.load(f)["n_after"]

# ── Visualisations ────────────────────────────────────────────────────────────

try:
    model.visualize_barchart(top_n_topics=n_after).write_image(
        os.path.join(OUTPUT_DIR, "barchart_final.pdf")
    )
    model.visualize_hierarchy().write_image(
        os.path.join(OUTPUT_DIR, "hierarchy_final.pdf")
    )
    print("  Sauvegardées en PDF.")
except Exception:
    model.visualize_barchart(top_n_topics=n_after).write_html(
        os.path.join(OUTPUT_DIR, "barchart_final.html")
    )
    model.visualize_hierarchy().write_html(
        os.path.join(OUTPUT_DIR, "hierarchy_final.html")
    )
    print("  Sauvegardées en HTML (kaleido non disponible pour PDF).")

# ── Sauvegarde modèle final ───────────────────────────────────────────────────

model.save(os.path.join(OUTPUT_DIR, "bertopic_ward_model_final"))

print("\nTerminé.")
print(f"Tous les fichiers sont dans : {OUTPUT_DIR}")
