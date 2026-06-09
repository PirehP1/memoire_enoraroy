"""
Vérification empirique de la loi de Zipf sur un corpus JSON.
(Basé sur la méthodologie simplifiée de https://codedrome.substack.com/p/zipfs-law-in-python)

La loi de Zipf : la fréquence d'un lemme est le réciproque de son rang 
multiplié par la fréquence la plus haute.
f(r) = f(1) * (1 / r)

Le script :
  1. Charge les lemmes du corpus avec filtres.
  2. Calcule les fréquences et range les lemmes par ordre décroissant.
  3. Applique la méthodologie de https://codedrome.substack.com/p/zipfs-law-in-python (C = fréquence max, alpha = 1).
  4. Exporte :
       - zipf_table.csv                  : rang, lemme, freq, fraction, freq_predite, diff, diff_%
       - zipf_parametres.csv             : C, α (fixé à 1)
       - zipf_plot_absolu.pdf            : fréquence vs rang (linéaire, sans droite théorique)
       - zipf_plot_absolu_theorique.pdf  : fréquence vs rang (linéaire, avec droite théorique)
       - zipf_plot_loglog.pdf            : fréquence vs rang (log-log, sans droite théorique)
       - zipf_plot_loglog_theorique.pdf  : fréquence vs rang (log-log, avec droite théorique)
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
    """Charge les lemmes du corpus avec les filtres demandés."""
    with open(corpus_path, encoding="utf-8") as f:
        data = json.load(f)

    nb_docs_total   = len(data)
    nb_docs_periode = 0
    lemmas          = []

    for doc in tqdm(data, desc="Lecture corpus", leave=False):
        meta = doc["document"]

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
    """Calcule les fréquences et classe les lemmes par rang décroissant."""
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
    La fréquence prévue (Zipf frequency) dépend uniquement de la fréquence 
    du mot le plus courant (rang 1).
    Donc C = fréquence max, et alpha est strictement égal à 1.
    """
    top_frequency = float(df.iloc[0]["freq"])

    return {
        "C":         top_frequency,
        "alpha":     1.0,           
        "R2":        np.nan,
        "p_value":   np.nan,
        "std_alpha": np.nan,
    }


def plot_zipf(
    df: pd.DataFrame,
    params: dict,
    out_dir: pathlib.Path,
) -> None:
    """Génère les graphiques d'analyse (échelle linéaire et log-log, avec et sans théorie)."""
    C, alpha = params["C"], params["alpha"]
    ranks = df["rang"].values
    freqs = df["freq"].values

    # Génération de la courbe théorique continue
    r_pred = np.linspace(ranks[0], ranks[-1], 500)
    f_pred = zipf_model(r_pred, C, alpha)

    # ─── ÉCHELLE LINÉAIRE ─────────────────────────────────────────────

    # Graphique 1 : Échelle linéaire - SANS droite théorique
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(ranks, freqs, lw=1.5, color="#2c7bb6", label="Fréquences observées")
    ax.set_xlabel("Rang", fontsize=11)
    ax.set_ylabel("Fréquence", fontsize=11)
    ax.set_title("Loi de Zipf — échelle linéaire (Données brutes)", fontsize=12)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.35)
    plt.tight_layout()
    plt.savefig(str(out_dir / "zipf_plot_absolu.pdf"), format="pdf", bbox_inches="tight")
    plt.close()
    print("  → zipf_plot_absolu.pdf (Sans courbe théorique)")

    # Graphique 2 : Échelle linéaire - AVEC droite théorique
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(ranks, freqs, lw=1.5, color="#2c7bb6", label="Fréquences observées")
    ax.plot(r_pred, f_pred, lw=2, ls="--", color="#d7191c", label=f"Modèle théorique (C={C:.0f}, α={alpha:.1f})")
    ax.set_xlabel("Rang", fontsize=11)
    ax.set_ylabel("Fréquence", fontsize=11)
    ax.set_title("Loi de Zipf — échelle linéaire (Comparaison)", fontsize=12)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.35)
    plt.tight_layout()
    plt.savefig(str(out_dir / "zipf_plot_absolu_theorique.pdf"), format="pdf", bbox_inches="tight")
    plt.close()
    print("  → zipf_plot_absolu_theorique.pdf (Avec courbe théorique)")


    # ─── ÉCHELLE LOG-LOG ──────────────────────────────────────────────

    # Graphique 3 : Log-Log - SANS droite théorique
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.loglog(ranks, freqs, lw=1.5, color="#2c7bb6", label="Fréquences observées")
    ax.set_xlabel("log(Rang)", fontsize=11)
    ax.set_ylabel("log(Fréquence)", fontsize=11)
    ax.set_title("Loi de Zipf — espace log-log (Données brutes)", fontsize=12)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.35, which="both")
    plt.tight_layout()
    plt.savefig(str(out_dir / "zipf_plot_loglog.pdf"), format="pdf", bbox_inches="tight")
    plt.close()
    print("  → zipf_plot_loglog.pdf (Sans droite théorique)")

    # Graphique 4 : Log-Log - AVEC droite théorique
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.loglog(ranks, freqs, lw=1.5, color="#2c7bb6", label="Fréquences observées")
    ax.loglog(r_pred, f_pred, lw=2, ls="--", color="#d7191c", 
              label=f"Ajustement Zipf \nC={C:.2f}, α={alpha:.3f}")
    ax.set_xlabel("log(Rang)", fontsize=11)
    ax.set_ylabel("log(Fréquence)", fontsize=11)
    ax.set_title("Loi de Zipf — espace log-log (Comparaison)", fontsize=12)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.35, which="both")
    plt.tight_layout()
    plt.savefig(str(out_dir / "zipf_plot_loglog_theorique.pdf"), format="pdf", bbox_inches="tight")
    plt.close()
    print("  → zipf_plot_loglog_theorique.pdf (Avec droite théorique)")


# ==========================================================
# PROGRAMME PRINCIPAL
# ==========================================================

def main():
    parser = argparse.ArgumentParser(
        description="Vérifie la loi de Zipf sur un corpus JSON."
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
    exclude_pos = set(args.exclude_pos)
    out_dir.mkdir(parents=True, exist_ok=True)

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
    print(df.head(10)[["rang", "lemme", "freq"]].to_string(index=False))

    print("\n── 3. Application du modèle ──────────────────────────────")
    params = fit_zipf(df)
    print(f"  C (Fréq max) = {params['C']:.0f}")
    print(f"  α (Alpha)    = {params['alpha']:.1f} (fixé par la méthode)")

    # ── 4. Calculs et Export CSV ──────────────────────────────────────
    print("\n── 4. Export CSV ─────────────────────────────────────────")
    
    df["zipf_fraction"] = "1/" + df["rang"].astype(str)
    df["freq_predite"] = params["C"] * (1 / df["rang"]) # zipf_frequency
    df["difference_actuelle"] = df["freq"] - df["freq_predite"]
    df["difference_pourcent"] = (df["freq"] / df["freq_predite"]) * 100

    df["freq_predite"] = df["freq_predite"].round(2)
    df["difference_actuelle"] = df["difference_actuelle"].round(2)
    df["difference_pourcent"] = df["difference_pourcent"].round(2)

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
