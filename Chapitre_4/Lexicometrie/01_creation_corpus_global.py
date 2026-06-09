#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=======================================================================
  SCRIPT 01 — CONSTRUCTION DU CORPUS (JSON)
  raw_texts/ + meta_lemmatisation.csv → corpus_complet.json
=======================================================================

DESCRIPTION
-----------
Ce script construit le corpus (annotation spaCy) à partir
des textes bruts stockés localement.

FILTRES APPLIQUÉS
-----------------
  • Année comprise entre 1975 et 2025 (inclus)
  • Exclusion du document 69825517c835c41957e003ac

STRUCTURE ATTENDUE
------------------
  <dossier du script>/
  ├── raw_texts/                  ← fichiers {doc_id}.txt
  ├── meta_lemmatisation.csv      ← métadonnées (doc_id, year, title)
  └── output/
      └── corpus_complet/
          └── corpus_complet.json ← sortie

USAGE
-----
  python 01_construction_corpus_global.py

DÉPENDANCES
-----------
  pip install spacy pandas tqdm lexploreur
  python -m spacy download en_core_web_lg
=======================================================================
"""

import sys
import pathlib
import pandas as pd
from tqdm import tqdm
#import depuis le repo https://github.com/leodumont/lexploreur
from lexploreur.corpus import corpus

BASE_DIR = pathlib.Path(__file__).resolve().parent

# Dossier contenant les fichiers {doc_id}.txt
RAW_DIR = BASE_DIR / "raw_texts"

# Fichier de métadonnées sur les textes 
META_CSV = BASE_DIR / "meta_lemmatisation.csv"

# Corpus JSON de sortie
OUT_DIR     = BASE_DIR / "output" / "corpus_complet"
CORPUS_JSON = OUT_DIR / "corpus_complet.json"

# Filtres
YEAR_MIN   = 1975
YEAR_MAX   = 2025
EXCLUDE_ID = "69825517c835c41957e003ac" #car ce document était vraiment problématique : multilingue, et ne portait pas vraiment sur le sujet

# Modèle spaCy
SPACY_MODEL = "en_core_web_lg"


def main():
    print("  SCRIPT 01 — CONSTRUCTION DU CORPUS")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if CORPUS_JSON.exists():
        print(f"\n  ↩  JSON déjà présent : {CORPUS_JSON}")
        print("     Supprimez-le pour forcer la ré-annotation spaCy.")
        return

    # ── 1. Chargement des métadonnées ─────────────────────────────────
    print(f"\n── 1. Chargement des métadonnées ({META_CSV.name})")
    if not META_CSV.exists():
        print(f"  [ERREUR] Fichier introuvable : {META_CSV}")
        print("  Assurez-vous d'avoir lancé 00_lemmatisation.py au préalable.")
        sys.exit(1)

    meta_df = pd.read_csv(META_CSV, encoding="utf-8-sig")
    print(f"  {len(meta_df):,} documents dans les métadonnées")

    # Colonnes minimales attendues
    for col in ("doc_id", "year"):
        if col not in meta_df.columns:
            print(f"  [ERREUR] Colonne manquante dans le CSV : '{col}'")
            sys.exit(1)

    # ── 2. Filtres ────────────────────────────────────────────────────
    print(f"\n── 2. Application des filtres")

    meta_df["year"] = pd.to_numeric(meta_df["year"], errors="coerce")

    before = len(meta_df)
    meta_df = meta_df.dropna(subset=["year"])
    dropped_no_year = before - len(meta_df)

    before = len(meta_df)
    meta_df = meta_df[
        (meta_df["year"] >= YEAR_MIN) & (meta_df["year"] <= YEAR_MAX)
    ]
    dropped_year = before - len(meta_df)

    before = len(meta_df)
    meta_df = meta_df[meta_df["doc_id"].astype(str) != EXCLUDE_ID]
    dropped_excl = before - len(meta_df)

    meta_df["year"] = meta_df["year"].astype(int)

    print(f"  Supprimés (année manquante)     : {dropped_no_year:,}")
    print(f"  Supprimés (hors {YEAR_MIN}-{YEAR_MAX})          : {dropped_year:,}")
    print(f"  Supprimés (id exclu)            : {dropped_excl:,}")
    print(f"  Documents retenus               : {len(meta_df):,}")

    # ── 3. Chargement des textes bruts ────────────────────────────────
    print(f"\n── 3. Chargement des textes bruts")
    print(f"  Dossier : {RAW_DIR}")
    if not RAW_DIR.exists():
        print(f"  [ERREUR] Dossier raw_texts introuvable : {RAW_DIR}")
        sys.exit(1)

    rows, missing = [], 0
    for _, row in tqdm(meta_df.iterrows(), total=len(meta_df),
                       desc="  Lecture raw_texts"):
        doc_id   = str(row["doc_id"])
        raw_file = RAW_DIR / f"{doc_id}.txt"

        if not raw_file.exists():
            missing += 1
            continue

        rows.append({
            "doc_id" : doc_id,
            "year"   : int(row["year"]),
            "title"  : row.get("title", ""),
            "texte"  : raw_file.read_text(encoding="utf-8", errors="replace"),
        })

    if missing:
        print(f"\n  [AVERTISSEMENT] {missing} fichiers .txt introuvables "
              f"(présents dans le CSV mais absents du dossier raw_texts)")

    df = pd.DataFrame(rows)
    print(f"\n  DataFrame final : {len(df):,} documents avec texte")

    if len(df) == 0:
        print("  [ERREUR] Aucun document à annoter. "
              "Vérifiez RAW_DIR et META_CSV.")
        sys.exit(1)

    # ── 4. Annotation spaCy → JSON  ─────────────────────────
    print(f"\n── 4. Annotation spaCy ({SPACY_MODEL}) → JSON ")
    print(f"  Cette étape peut prendre plusieurs dizaines de minutes.")
    print(f"  Sortie : {CORPUS_JSON}\n")

    corpus(
        df,
        corpus_name = str(CORPUS_JSON),
        text_column = "texte",
        spacy_model = SPACY_MODEL,
        ner         = False,
    )

    print(f"\n Corpus JSON créé → {CORPUS_JSON.resolve()}")
    print(f"  Nb documents annotés : {len(df):,}")
    print(f"  Plage temporelle     : {df['year'].min()} – {df['year'].max()}")

if __name__ == "__main__":
    main()
