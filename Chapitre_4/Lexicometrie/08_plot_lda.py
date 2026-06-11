"""
  SCRIPT 08 — VISUALISATION DU MODÈLE LDA

Lit les fichiers produits par 07_LDA_k.py et génère :

  1. Graphiques d'évolution temporelle (moyenne de γ par année, sans
     seuil de présence — Griffiths & Steyvers, 2004)

  2. Visualisation interactive HTML (pyLDAvis) à ouvrir dans un
     navigateur (optionnel — nécessite pip install pyldavis)

SORTIES
-------
  output/topic_modelling/
    topic_mean_gamma_by_year.csv        ← moyenne de γ par topic et par année
    05_ruptures_courbes_individuelles.pdf
    06_evolution_globale_stacked.pdf
    ldavis.html                         ← si pyLDAvis est installé

STRUCTURE ATTENDUE
------------------
  <dossier du script>/
  ├── output/topic_modelling/
  │   ├── gamma_df.csv            ← produit par 07_LDA_k.py
  │   ├── topics_lda.csv          ← produit par 07_LDA_k.py
  │   └── lda_model/              ← produit par 07_LDA_k.py
  │       ├── lda.model
  │       └── dictionary.gensim
  ├── output/corpus_propre/corpus_propre.json
  ├── stopwords-en.txt
  └── meta_lemmatisation.csv      ← optionnel, pour les années


PRÉ-REQUIS
----------
  python 07_LDA_k.py

DÉPENDANCES
-----------
  pip install numpy pandas matplotlib seaborn ruptures
  pip install pyldavis   ← optionnel, pour ldavis.html
"""

import json
import pathlib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
import ruptures as rpt

BASE_DIR = pathlib.Path(__file__).resolve().parent

CORPUS_JSON    = BASE_DIR / "output" / "corpus_propre" / "corpus_propre.json"
STOPWORDS_PATH = BASE_DIR / "stopwords-en.txt"
META_CSV       = BASE_DIR / "meta_lemmatisation.csv"

MODEL_DIR  = BASE_DIR / "output" / "topic_modelling" / "lda_model"
OUT_DIR    = BASE_DIR / "output" / "topic_modelling"
GAMMA_CSV  = OUT_DIR / "gamma_df.csv"
TOPICS_CSV = OUT_DIR / "topics_lda.csv"

# Identiques à 07_LDA_k.py — NE PAS MODIFIER
EXCLUDE_POS = ["PUNCT", "CCONJ", "DET", "ADP", "PRON", "PART", "SCONJ",
               "SPACE", "SYM", "NUM", "X", "AUX", "INTJ"]

EXCLUDE_TOKENS = ["-", "--", "…", "'s", "n't", "'re", "'ve", "'d", "'ll",
                  "https", "http", "see", "however", "also", "university",
                  "die", "von", "der", "den", "zur", "lo", "di", "lot",
                  "o6p", "xl", "dq", "на", "g6", "g12", "iii", "ap", "rrr", "rr",
                  "wkh", "oc", "robert", "kerala", "bäyrämova", "torigni",
                  "avranches", "dl", "……", "reproduction", "tí", "press", "walter"]

MANUAL_PENALTY = 15
LINE_COLOR     = "#2c7bb6"


def load_years(n_docs):
    if META_CSV.exists():
        meta = pd.read_csv(META_CSV, encoding="utf-8-sig")
        if "year" in meta.columns and len(meta) == n_docs:
            print(f"  Années chargées depuis : {META_CSV}")
            return pd.to_numeric(meta["year"], errors="coerce").reset_index(drop=True)
    print(f"  Extraction des années depuis : {CORPUS_JSON}")
    with open(CORPUS_JSON, encoding="utf-8", errors="replace") as f:
        data = json.load(f)
    docs  = data if isinstance(data, list) else data.get("docs", [])
    years = [entry.get("document", entry).get("year") for entry in docs[:n_docs]]
    while len(years) < n_docs:
        years.append(None)
    return pd.to_numeric(pd.Series(years), errors="coerce")

if __name__ == "__main__":

    for f in [GAMMA_CSV, TOPICS_CSV]:
        if not f.exists():
            print(f"[ERREUR] Fichier introuvable : {f}")
            print("→ Lancez d'abord 07_LDA_k.py")
            exit()

    gamma_df  = pd.read_csv(GAMMA_CSV, index_col=0)
    df_topics = pd.read_csv(TOPICS_CSV)

    topic_cols = [c for c in gamma_df.columns if c.startswith("T")]
    num_topics = len(topic_cols)

    # ── Années ────────────────────────────────────────────────────────
    years_s = load_years(len(gamma_df))
    gamma_df["year"] = years_s.values
    gamma_df = gamma_df.dropna(subset=["year"])
    gamma_df["year"] = gamma_df["year"].astype(int)
    print(f"  {len(gamma_df)} documents avec année "
          f"({gamma_df['year'].min()}–{gamma_df['year'].max()})")

    df_mean = gamma_df.groupby("year")[topic_cols].mean()
    df_mean = df_mean.sort_index()
    df_mean.to_csv(OUT_DIR / "topic_mean_gamma_by_year.csv",
                   index_label="year", encoding="utf-8-sig")
    print("  → topic_mean_gamma_by_year.csv")

    years = df_mean.index.values

    # Labels : "T0 — mot1 / mot2 / mot3  (γ moy.=0.08)"
    topic_labels = {}
    for tid, col in enumerate(topic_cols):
        mots    = " / ".join(df_topics[df_topics["topic_id"] == tid].head(3)["mot"])
        moy_glo = gamma_df[col].mean()
        topic_labels[col] = f"{col} — {mots}  (γ moy.={moy_glo:.3f})"

    # ── Plot 1 : courbes individuelles + détection de ruptures ────────
    print(f"\n── Courbes individuelles (pénalité={MANUAL_PENALTY}) ─────────")

    # Échelle commune à tous les subplots pour permettre la comparaison
    y_max_global = df_mean[topic_cols].max().max() * 1.1   # +10 % de marge

    ncols = 2
    nrows = (num_topics + 1) // 2
    fig, axes = plt.subplots(nrows=nrows, ncols=ncols,
                             figsize=(14, 4 * nrows), sharex=True, sharey=True)
    axes = axes.flatten()

    for i, col in enumerate(topic_cols):
        ax     = axes[i]
        signal = df_mean[col].values

        ax.plot(years, signal, color=LINE_COLOR, lw=2, marker="o", ms=4, zorder=3)
        ax.fill_between(years, signal, color=LINE_COLOR, alpha=0.1)
        ax.set_ylim(0, y_max_global)

        # Détection de ruptures (ruptures.Pelt)
        if len(signal) >= 5 and np.std(signal) > 1e-4:
            algo = rpt.Pelt(model="normal", min_size=3).fit(signal)
            try:
                result = algo.predict(pen=MANUAL_PENALTY)
                ymax   = ax.get_ylim()[1]
                for bkp in result[:-1]:
                    year_bkp = years[min(bkp, len(years) - 1)]
                    ax.axvline(x=year_bkp, color="#d7191c", ls="--", lw=1.5, zorder=5)
                    ax.text(year_bkp + 0.1, ymax * 0.85, f"{year_bkp}",
                            color="#d7191c", fontsize=8, fontweight="bold",
                            bbox=dict(facecolor="white", alpha=0.7, edgecolor="none"))
            except Exception:
                pass

        ax.set_title(topic_labels[col], fontsize=10, loc="left", fontweight="bold")
        ax.set_ylabel("γ moyen", fontsize=8)
        ax.grid(axis="y", alpha=0.2, ls=":")
        ax.tick_params(labelsize=8)

    for j in range(num_topics, len(axes)):
        fig.delaxes(axes[j])

    plt.suptitle(
        "Évolution de la probabilité moyenne (γ) par topic et par année\n"
        "(valeurs continues, d'après Griffiths & Steyvers, 2004)",
        fontsize=11, y=1.01,
    )
    plt.tight_layout()
    plt.savefig(OUT_DIR / "05_ruptures_courbes_individuelles.pdf",
                format="pdf", bbox_inches="tight")
    plt.close()
    print("  → 05_ruptures_courbes_individuelles.pdf")

    # ── Plot 2 : stacked bar chart (proportions relatives) ─────────────
    # On normalise les γ moyens pour obtenir la part relative de chaque
    # topic dans le mix thématique annuel.
    print("\n── Stacked bar chart ─────────────────────────────────────────")

    df_norm = df_mean.div(df_mean.sum(axis=1), axis=0) * 100

    palette = (sns.color_palette("tab10", num_topics) if num_topics <= 10
               else sns.color_palette("tab20", num_topics))

    fig_stack, ax_stack = plt.subplots(figsize=(12, 7))
    df_norm.plot(kind="bar", stacked=True, ax=ax_stack,
                 color=palette, width=0.8)

    ax_stack.set_title(
        "Évolution de la structure thématique — proportions relatives des γ moyens",
        fontsize=13, pad=15,
    )
    ax_stack.set_ylabel("Part relative du topic (%)", fontsize=11)
    ax_stack.set_xlabel("Année", fontsize=11)
    ax_stack.set_ylim(0, 100)

    handles, labels_leg = ax_stack.get_legend_handles_labels()
    new_labels = [topic_labels.get(l, l) for l in labels_leg]
    ax_stack.legend(handles, new_labels, title="Topics",
                    bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=8)

    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(OUT_DIR / "06_evolution_globale_stacked.pdf",
                format="pdf", bbox_inches="tight")
    plt.close()
    print("  → 06_evolution_globale_stacked.pdf")

    print(f"\nTerminé — {num_topics} topics | {len(gamma_df)} documents avec année")

    # ── pyLDAvis (optionnel) ───────────────────────────────────────────
    print("\n── pyLDAvis ──────────────────────────────────────────────────")
    try:
        import pyLDAvis
        import pyLDAvis.gensim_models as gensimvis
        from gensim.models import LdaModel
        from gensim import corpora
        from lexploreur.corpus import lexical_view
    except ImportError as e:
        print(f"  [IGNORÉ] {e}")
        print("  Installez pyLDAvis avec : pip install pyldavis")
    else:
        model_path = MODEL_DIR / "lda.model"
        dict_path  = MODEL_DIR / "dictionary.gensim"
        if not model_path.exists() or not dict_path.exists():
            print(f"  [IGNORÉ] Modèle introuvable dans {MODEL_DIR}")
            print("  Lancez d'abord 07_LDA_k.py")
        else:
            print("  Chargement du modèle et reconstruction du corpus …")
            lda_model  = LdaModel.load(str(model_path))
            dictionary = corpora.Dictionary.load(str(dict_path))

            with open(STOPWORDS_PATH, encoding="utf-8", errors="replace") as f:
                stopwords = [line.strip() for line in f if line.strip()]

            df_lv = lexical_view(
                str(CORPUS_JSON),
                feature_to_extract = "lemma",
                stopwords          = stopwords,
                lowercase          = True,
                exclude_pos        = EXCLUDE_POS,
                exclude_tokens     = EXCLUDE_TOKENS,
            )
            df_lv["lemma"] = df_lv["lemma"].apply(
                lambda tokens: [t for t in tokens if len(t) > 1]
            )
            corpus_bow = [dictionary.doc2bow(tokens) for tokens in df_lv["lemma"]]

            print("  Préparation pyLDAvis (1–3 min selon la taille du corpus) …")
            vis_data = gensimvis.prepare(
                lda_model,
                corpus_bow,
                dictionary,
                sort_topics = True,
                mds         = "mmds",
                n_jobs      = 1,
            )
            out_html = OUT_DIR / "ldavis.html"
            pyLDAvis.save_html(vis_data, str(out_html))
            print(f"  → ldavis.html")
