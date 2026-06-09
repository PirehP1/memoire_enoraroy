"""
Vérification empirique de la loi de Zipf sur un corpus JSON.

La loi de Zipf : la fréquence d'un lemme est inversement
proportionnelle à son rang : f(r) = C / r^α, avec α ≈ 1 pour la
plupart des langues naturelles.

Le script :
  1. Charge les lemmes du corpus en appliquant un filtre chronologique,
     un filtre alphabétique (lemmes non purement alphabétiques exclus)
     et un filtre de longueur minimale (< 3 caractères exclus).
  2. Calcule les fréquences et range les lemmes par ordre décroissant.
  3. Ajuste f(r) = C * r^(-α) par régression log-log (linregress).
     Note : contrairement à la loi de Heap (données cumulatives),
     les points rang/fréquence sont indépendants → linregress est ici
     méthodologiquement correct et R², p-value sont interprétables.
  4. Exporte :
       - zipf_table.csv          : rang, lemme, fréquence, fréquence prédite
       - zipf_parametres.csv     : C, α, R², p-value, écart-type
       - zipf_plot_absolu.pdf    : fréquence vs rang (échelle linéaire)
       - zipf_plot_loglog.pdf    : fréquence vs rang (log-log + droite ajustée)

Usage :
    python loi_zipf.py corpus_propre.json
    python loi_zipf.py corpus_propre.json \\
        --year-min 1980 --year-max 2020 \\
        --output output/zipf \\
        --exclude-pos PUNCT NUM
"""

import argparse
import json
import pathlib
from collections import Counter

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.stats import linregress
from tqdm import tqdm


def zipf_model(rank: np.ndarray, C: float, alpha: float) -> np.ndarray:
    """Modèle de Zipf : f(r) = C * r^(-α)."""
    return C * np.power(rank, -alpha)


def load_lemmas(
    corpus_path: pathlib.Path,
    year_min: int,
    year_max: int,
    exclude_pos: set,
) -> tuple:
    """
    Charge les lemmes du corpus en appliquant trois filtres :
    - Filtre chronologique : seuls les documents dans [year_min, year_max].
    - Filtre alphabétique : lemmes non purement alphabétiques exclus
      (chiffres, tirets, ponctuations isolés).
    - Filtre de longueur : lemmes de moins de 3 caractères exclus
      (articles, prépositions fréquents qui bruiteraient la distribution).
    - Filtre POS (optionnel) : catégories morphosyntaxiques à exclure.

    Retourne (lemmes, nb_docs_total, nb_docs_période).
    """
    with open(corpus_path, encoding="utf-8") as f:
        data = json.load(f)

    nb_docs_total   = len(data)
    nb_docs_periode = 0
    lemmas          = []

    for doc in tqdm(data, desc="Lecture corpus", leave=False):
        meta = doc["document"]

        # Conversion robuste de l'année (peut être str ou int dans le JSON)
        try:
            year = int(meta.get("year"))
        except (TypeError, ValueError):
            continue

        if not (year_min <= year <= year_max):
            continue

        nb_docs_periode += 1

        for tok in meta.get("lexical_features", []):
            pos   = tok.get("pos", "")
            lemma = tok.get("lemma", "").lower()

            if pos in exclude_pos:
                continue
            if not lemma.isalpha():
                continue
            if len(lemma) < 3:
                continue

            lemmas.append(lemma)

    return lemmas, nb_docs_total, nb_docs_periode


def compute_zipf(lemmas: list) -> pd.DataFrame:
    """
    Calcule les fréquences et classe les lemmes par rang décroissant.

    Retourne un DataFrame avec colonnes : rang, lemme, freq.
    """
    freq = Counter(lemmas)
    df = (
        pd.DataFrame(freq.items(), columns=["lemme", "freq"])
        .sort_values("freq", ascending=False)
        .reset_index(drop=True)
    )
    df.insert(0, "rang", df.index + 1)
    return df


def fit_zipf(df: pd.DataFrame) -> dict:
    """
    Ajuste la loi de Zipf par régression linéaire dans l'espace log-log :
        log(f) = log(C) − α * log(r)

    Les points rang/fréquence sont indépendants (pas de données cumulatives),
    donc linregress est méthodologiquement approprié : R² et p-value
    sont directement interprétables.

    Pour la langue naturelle, α ≈ 1 (loi de Zipf stricte).
    α < 1 signifie une distribution plus étalée (vocabulaire riche).
    α > 1 signifie une concentration plus forte sur les mots fréquents.

    Retourne un dictionnaire avec C, α, R², p-value, std_alpha.
    """
    log_r = np.log(df["rang"].values.astype(float))
    log_f = np.log(df["freq"].values.astype(float))

    slope, intercept, r_value, p_value, std_err = linregress(log_r, log_f)

    return {
        "C":         np.exp(intercept),
        "alpha":     -slope,             # α = -pente dans log(f) = log(C) - α*log(r)
        "R2":        r_value ** 2,
        "p_value":   p_value,
        "std_alpha": std_err,
    }


def plot_zipf(
    df: pd.DataFrame,
    params: dict,
    out_dir: pathlib.Path,
) -> None:
    """
    Génère deux graphiques sauvegardés en PDF :

    - zipf_plot_absolu.pdf : fréquence vs rang en échelle linéaire.
      Montre la forme caractéristique en L de la distribution de Zipf.

    - zipf_plot_loglog.pdf : fréquence vs rang en échelle log-log.
      La droite ajustée (pente = -α) confirme la conformité à la loi.
      Une déviation dans les hauts rangs (mots rares) est normale.
    """
    C, alpha, r2 = params["C"], params["alpha"], params["R2"]
    ranks = df["rang"].values
    freqs = df["freq"].values

    # Courbe ajustée
    r_pred = np.linspace(ranks[0], ranks[-1], 500)
    f_pred = zipf_model(r_pred, C, alpha)

    # Graphique 1 : échelle linéaire
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(ranks, freqs, lw=1.5, color="#2c7bb6", label="Fréquences observées")
    ax.set_xlabel("Rang", fontsize=11)
    ax.set_ylabel("Fréquence", fontsize=11)
    ax.set_title("Loi de Zipf — échelle linéaire", fontsize=12)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.35)
    plt.tight_layout()
    plt.savefig(str(out_dir / "zipf_plot_absolu.pdf"), format="pdf", bbox_inches="tight")
    plt.close()
    print("  → zipf_plot_absolu.pdf")

    # Graphique 2 : log-log avec droite ajustée
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.loglog(ranks, freqs,
              lw=1.5, color="#2c7bb6", label="Fréquences observées")
    ax.loglog(r_pred, f_pred,
              lw=2, ls="--", color="#d7191c",
              label=f"Ajustement Zipf\nC={C:.2f}, α={alpha:.3f}, R²={r2:.4f}")
    ax.set_xlabel("log(Rang)", fontsize=11)
    ax.set_ylabel("log(Fréquence)", fontsize=11)
    ax.set_title("Loi de Zipf — espace log-log\n(droite = conformité parfaite)",
                 fontsize=12)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.35, which="both")
    plt.tight_layout()
    plt.savefig(str(out_dir / "zipf_plot_loglog.pdf"), format="pdf", bbox_inches="tight")
    plt.close()
    print("  → zipf_plot_loglog.pdf")

def main():
    parser = argparse.ArgumentParser(
        description="Vérifie la loi de Zipf sur un corpus JSON et exporte les résultats."
    )
    parser.add_argument("corpus",
        help="Chemin vers le fichier corpus JSON.")
    parser.add_argument("--year-min", type=int, default=1975, dest="year_min",
        help="Première année à inclure (défaut : 1975).")
    parser.add_argument("--year-max", type=int, default=2025, dest="year_max",
        help="Dernière année à inclure (défaut : 2025).")
    parser.add_argument("--output", default="output/zipf",
        help="Dossier de sortie (défaut : output/zipf/).")
    parser.add_argument("--exclude-pos", nargs="*", default=[], dest="exclude_pos",
        help="Catégories POS à exclure, ex : --exclude-pos PUNCT NUM DET.")
    args = parser.parse_args()

    out_dir     = pathlib.Path(args.output)
    exclude_pos = set(args.exclude_pos)   # set() correct, pas {}
    out_dir.mkdir(parents=True, exist_ok=True)

    print("  LOI DE ZIPF — CORPUS")

    # ── 1. Chargement ─────────────────────────────────────────────────
    print("\n── 1. Chargement du corpus ───────────────────────────────")
    lemmas, nb_total, nb_periode = load_lemmas(
        pathlib.Path(args.corpus),
        args.year_min, args.year_max,
        exclude_pos,
    )
    print(f"  Documents total           : {nb_total:,}")
    print(f"  Documents période retenue : {nb_periode:,}")
    print(f"  Tokens retenus            : {len(lemmas):,}")

    if not lemmas:
        print("\n[ERREUR] Aucun lemme chargé. Vérifiez le corpus et les paramètres.")
        return

    # ── 2. Fréquences et rang ─────────────────────────────────────────
    print("\n── 2. Calcul des fréquences ──────────────────────────────")
    df = compute_zipf(lemmas)
    print(f"  Lemmes uniques : {len(df):,}")
    print("\n  Top 10 lemmes :")
    print(df.head(10).to_string(index=False))

    # ── 3. Ajustement log-log ─────────────────────────────────────────
    print("\n── 3. Ajustement log-log ─────────────────────────────────")
    params = fit_zipf(df)
    print(f"  C        = {params['C']:.4f}")
    print(f"  α        = {params['alpha']:.4f}  (±{params['std_alpha']:.4f})   (≈ 1 attendu)")
    print(f"  R²       = {params['R2']:.6f}")
    print(f"  p        = {params['p_value']:.2e}")

    alpha = params["alpha"]
    if 0.8 <= alpha <= 1.2:
        print(" α dans [0.8, 1.2] : conforme à la loi de Zipf")
    elif alpha < 0.8:
        print(" α < 0.8 : distribution plus étalée (vocabulaire riche)")
    else:
        print(" α > 1.2 : concentration plus forte sur les mots fréquents")

    # ── 4. Export CSV ─────────────────────────────────────────────────
    print("\n── 4. Export CSV ─────────────────────────────────────────")
    df["freq_predite"] = zipf_model(
        df["rang"].values.astype(float), params["C"], params["alpha"]
    ).astype(int)
    df.to_csv(out_dir / "zipf_table.csv", index=False, encoding="utf-8-sig")
    print("  → zipf_table.csv")

    pd.DataFrame([params]).to_csv(
        out_dir / "zipf_parametres.csv", index=False, encoding="utf-8-sig"
    )
    print("  → zipf_parametres.csv")

    # ── 5. Graphiques ─────────────────────────────────────────────────
    print("\n── 5. Génération des graphiques ──────────────────────────")
    plot_zipf(df, params, out_dir)

    print(f"\n{'=' * 60}")
    print(f"  ✓ Terminé → {out_dir.resolve()}")
    print("=" * 60)


if __name__ == "__main__":
    main()
