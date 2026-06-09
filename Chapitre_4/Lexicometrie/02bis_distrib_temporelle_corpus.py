#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Distribution temporelle du corpus : tokens et documents par année.

Génère une planche comparative PDF à deux panneaux :
  1. Volume de tokens par année (corpus d'analyse uniquement).
  2. Nombre de documents par année : superposition de la base
     bibliographique MongoDB (fond bleu) et du corpus d'analyse (rouge).

Ce script est un outil de statistiques descriptives. Il se place juste
après la construction de corpus_propre.json, avant toute analyse lexicale.

Usage :
    python distribution_temporelle.py corpus_propre.json
    python distribution_temporelle.py corpus_propre.json \\
        --year-min 1980 --year-max 2020 \\
        --output output/distribution \\
        --mongo-uri mongodb://localhost:27017/ \\
        --mongo-db references_biblio_mongo \\
        --mongo-collection references
"""

import argparse
import json
import pathlib
import sys
import warnings

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")   # Backend sans affichage (script batch ou serveur)
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from tqdm import tqdm
from pymongo import MongoClient

warnings.filterwarnings("ignore")

# Palette chromatique
COLOR_TOKENS = "#636e72"  # Anthracite : volume de tokens
COLOR_BD     = "#2c7bb6"  # Bleu       : base bibliographique MongoDB
COLOR_CORPUS = "#d7191c"  # Rouge      : corpus d'analyse


# ==========================================================
# CHARGEMENT DU CORPUS JSON
# ==========================================================

def load_corpus_data(path: str, year_min: int, year_max: int) -> pd.DataFrame:
    """
    Charge le corpus JSON et retourne un DataFrame avec une ligne par
    document valide (year dans [year_min, year_max]).

    Colonnes produites : year (int), nb_tokens (int).
    Les documents avec une année absente ou non convertible sont ignorés.
    """
    p = pathlib.Path(path)
    if not p.exists():
        sys.exit(f"[ERREUR] Corpus introuvable : {p}")

    with open(p, encoding="utf-8", errors="replace") as f:
        data = json.load(f)

    records = []
    for item in data:
        if not isinstance(item, dict):
            continue
        doc      = item.get("document", item)
        year     = doc.get("year")
        nb_tokens = len(doc.get("lexical_features", []))

        try:
            y = int(year)
            if year_min <= y <= year_max:
                records.append({"year": y, "nb_tokens": nb_tokens})
        except (TypeError, ValueError):
            pass   # Année manquante ou non numérique : document ignoré

    return pd.DataFrame(records)


# ==========================================================
# CHARGEMENT DE LA BASE BIBLIOGRAPHIQUE MONGODB
# ==========================================================

def load_mongo_years(
    mongo_uri: str,
    db_name: str,
    collection_name: str,
    year_min: int,
    year_max: int,
) -> list:
    """
    Interroge la collection MongoDB pour récupérer l'année de toutes les
    références anglophones dans la plage [year_min, year_max].

    Ces données servent à contextualiser le corpus dans la planche :
    elles représentent la "base disponible" dont le corpus est un sous-ensemble.

    Retourne une liste vide si MongoDB est inaccessible (mode dégradé : la
    planche est générée sans la couche bibliographique).
    """
    try:
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        client.server_info()   # Déclenche l'exception si le serveur ne répond pas
    except Exception as e:
        print(f"[WARNING] MongoDB inaccessible : {e}. Planche générée sans la base biblio.")
        return []

    col = client[db_name][collection_name]
    query = {
        "$or": [
            {"language_iso": "en"},
            {"language": {"$in": ["English", "english", "EN", "eng"]}},
        ],
        "year": {"$gte": year_min, "$lte": year_max},
    }

    years = []
    for doc in tqdm(col.find(query, {"year": 1, "_id": 0}),
                    desc="Chargement MongoDB", leave=False):
        try:
            y = int(doc["year"])
            if year_min <= y <= year_max:
                years.append(y)
        except (TypeError, ValueError, KeyError):
            pass   # Année manquante ou malformée : référence ignorée

    client.close()
    return years


# ==========================================================
# VISUALISATION
# ==========================================================

def plot_combined_dashboard(
    df_corpus:   pd.DataFrame,
    years_mongo: list,
    year_min:    int,
    year_max:    int,
    out_dir:     pathlib.Path,
) -> None:
    """
    Génère une planche PDF à deux panneaux :

    Panneau 1 — Volume de tokens par année (corpus uniquement).
      Donne un aperçu de la densité informationnelle du corpus :
      une année avec peu de documents mais de longs textes peut avoir
      autant de tokens qu'une année à fort volume documentaire.

    Panneau 2 — Nombre de documents par année.
      Superpose deux séries :
        - Base bibliographique MongoDB (fond bleu) : tous les articles
          anglophones disponibles dans la base sur la période.
        - Corpus d'analyse (rouge, avant-plan) : les documents
          effectivement retenus.
      Cela permet de visualiser le taux de couverture du corpus
      par rapport à la littérature disponible.
      Si MongoDB n'est pas disponible, seul le corpus est affiché.
    """
    all_years = np.arange(year_min, year_max + 1)

    # Agrégations corpus
    tokens_per_year = (
        df_corpus.groupby("year")["nb_tokens"]
        .sum()
        .reindex(all_years, fill_value=0)
    )
    docs_corpus  = df_corpus["year"].value_counts().reindex(all_years, fill_value=0)
    total_tokens = int(tokens_per_year.sum())
    total_docs   = int(docs_corpus.sum())

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 10), sharex=True)

    # ── Panneau 1 : tokens ───────────────────────────────────────────
    ax1.bar(all_years, tokens_per_year, color=COLOR_TOKENS, alpha=0.7,
            label=f"Volume de tokens (N={total_tokens:,})")
    ax1.set_title("Volume de tokens par année — Corpus d'analyse",
                  fontsize=14, fontweight="bold", pad=15)
    ax1.set_ylabel("Nombre de tokens", fontsize=11)
    ax1.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: format(int(x), ","))
    )
    ax1.grid(True, axis="y", ls=":", alpha=0.6)
    ax1.legend()

    # ── Panneau 2 : documents ────────────────────────────────────────
    # Couche de fond : base bibliographique MongoDB (si disponible)
    if years_mongo:
        docs_mongo  = (
            pd.Series(years_mongo)
            .value_counts()
            .reindex(all_years, fill_value=0)
        )
        total_mongo = int(docs_mongo.sum())
        ax2.bar(all_years, docs_mongo,
                color=COLOR_BD, alpha=0.5,
                label=f"Base bibliographique (N={total_mongo:,})")

    # Avant-plan : corpus d'analyse
    ax2.bar(all_years, docs_corpus,
            color=COLOR_CORPUS, alpha=0.8,
            label=f"Corpus d'analyse (N={total_docs:,})")

    ax2.set_title("Nombre de documents par année — Base bibliographique vs Corpus",
                  fontsize=14, fontweight="bold", pad=15)
    ax2.set_ylabel("Nombre de documents", fontsize=11)
    ax2.set_xlabel("Années", fontsize=12)
    ax2.set_xticks(all_years[::2])
    ax2.tick_params(axis="x", rotation=45)
    ax2.grid(True, axis="y", ls=":", alpha=0.6)
    ax2.legend()

    plt.tight_layout()
    out_path = out_dir / "planche_tokens_documents.pdf"
    plt.savefig(out_path, format="pdf", bbox_inches="tight")
    print(f"  → {out_path}")
    plt.close()


# ==========================================================
# POINT D'ENTRÉE
# ==========================================================

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Génère une planche PDF de la distribution temporelle "
            "(tokens et documents) d'un corpus JSON."
        )
    )
    parser.add_argument("corpus",
        help="Chemin vers le fichier corpus JSON.")
    parser.add_argument("--year-min",  type=int, default=1975, dest="year_min",
        help="Première année à inclure (défaut : 1975).")
    parser.add_argument("--year-max",  type=int, default=2025, dest="year_max",
        help="Dernière année à inclure (défaut : 2025).")
    parser.add_argument("--output",    default="output/distribution_temporelle",
        help="Dossier de sortie (défaut : output/distribution_temporelle/).")
    parser.add_argument("--mongo-uri", default="mongodb://localhost:27017/",
        dest="mongo_uri",
        help="URI MongoDB (défaut : mongodb://localhost:27017/).")
    parser.add_argument("--mongo-db",  default="references_biblio_mongo",
        dest="mongo_db",
        help="Nom de la base MongoDB (défaut : references_biblio_mongo).")
    parser.add_argument("--mongo-collection", default="references",
        dest="mongo_collection",
        help="Nom de la collection MongoDB (défaut : references).")
    args = parser.parse_args()

    out_dir = pathlib.Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Chargement du corpus
    print(f"\nChargement du corpus : {args.corpus}")
    df_corpus = load_corpus_data(args.corpus, args.year_min, args.year_max)
    print(f"  {len(df_corpus):,} documents chargés.")
    print(f"  {df_corpus['nb_tokens'].sum():,} tokens au total.")

    # Chargement MongoDB (optionnel — mode dégradé si inaccessible)
    print("\nChargement de la base bibliographique MongoDB...")
    years_mongo = load_mongo_years(
        args.mongo_uri, args.mongo_db, args.mongo_collection,
        args.year_min, args.year_max,
    )
    if years_mongo:
        print(f"  {len(years_mongo):,} références chargées.")

    # Génération de la planche
    print("\nGénération de la planche...")
    plot_combined_dashboard(
        df_corpus, years_mongo,
        args.year_min, args.year_max, out_dir,
    )


if __name__ == "__main__":
    main()
