#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=======================================================================
  SCRIPT 01bis — CONSTRUCTION DU CORPUS PROPRE (JSON après prétraitement)
  raw_texts/ + _cooc_exclusions.py → corpus_propre.json
=======================================================================

DESCRIPTION
-----------
Ce script construit un SECOND corpus lexploreur (annotation spaCy)
après nettoyage des textes bruts selon deux couches :

  COUCHE 1 — Segments d'exclusion (EXCLUSION_SEGMENTS)
    → Supprime les titres bibliographiques, prénoms, toponymes, etc.
      repérés dans _cooc_exclusions.py autour des formes barbar*.
    → Ces segments sont remplacés par un espace.

  COUCHE 2 — Bruit bibliographique bib (BIB_PATTERNS / _TOKENS)
    → Supprime les abréviations (pp., vol., ibid., sq., fol., ms., ...),
      numérations romaines isolées, dates entre parenthèses, artefacts
      OCR (urls, guillemets orphelins, tirets multiples, etc.).
    → Les deux listes sont définies dans _cooc_exclusions.py.

POURQUOI UN SECOND JSON ?
--------------------------
Le corpus_complet.json (script 01) conserve le texte brut intégral pour
les statistiques avant prétraitement.
Le corpus_propre.json (ce script) sert aux analyses quantitatives :
  03_analyse_lexicale.py, 04_topic_modelling_LDA.py, cooc.py, etc.

FILTRES APPLIQUÉS (identiques au script 01)
--------------------------------------------
  • Année comprise entre YEAR_MIN et YEAR_MAX (inclus)
  • Exclusion du document EXCLUDE_ID

STRUCTURE ATTENDUE
------------------
  <dossier du script>/
  ├── raw_texts/                  ← fichiers {doc_id}.txt
  ├── meta_lemmatisation.csv      ← métadonnées (doc_id, year, title)
  ├── _cooc_exclusions.py         ← segments et patterns de nettoyage
  └── output/
      └── corpus_propre/
          └── corpus_propre.json  ← sortie

DÉPENDANCES
-----------
  pip install spacy pandas tqdm lexploreur
  python -m spacy download en_core_web_lg
=======================================================================
"""

import sys
import re
import pathlib
from collections import Counter, defaultdict

import pandas as pd
from tqdm import tqdm

from lexploreur.corpus import corpus

# ── Exclusions partagées ──────────────────────────────────────────────
from _cooc_exclusions import (
    EXCLUSION_SEGMENTS,
    BIB_TOKENS,
    BIB_PATTERNS,
    clean_text_bib,
)


BASE_DIR = pathlib.Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "raw_texts"
META_CSV = BASE_DIR / "meta_lemmatisation.csv"

OUT_DIR     = BASE_DIR / "output" / "corpus_propre"
CORPUS_JSON = OUT_DIR / "corpus_propre.json"

# Filtres temporels et d'exclusion
YEAR_MIN   = 1975
YEAR_MAX   = 2025
EXCLUDE_ID = "69825517c835c41957e003ac"

# Modèle spaCy
SPACY_MODEL = "en_core_web_lg"

# Mode audit : affiche un échantillon de textes avant/après nettoyage
AUDIT_SAMPLE = 5   # nb de documents à afficher (0 = pas d'audit)

# ──────────────────────────────────────────────────────────────────────
# RAPPORT DE NETTOYAGE — suivi de l'impact par couche
# ──────────────────────────────────────────────────────────────────────

class CleaningReport:
    """Collecte les statistiques de nettoyage pour le rapport final."""

    def __init__(self):
        self.n_docs          = 0
        self.chars_before    = 0
        self.chars_after     = 0
        self.segments_hits   = Counter()   # nb de hits par catégorie
        self.bib_hits    = 0           # nb total de suppressions bib
        self.docs_unchanged  = 0

    def add(self, doc_id: str, before: str, after: str,
            seg_cats: Counter, lam_hits: int):
        self.n_docs       += 1
        self.chars_before += len(before)
        self.chars_after  += len(after)
        self.segments_hits += seg_cats
        self.bib_hits  += lam_hits
        if before == after:
            self.docs_unchanged += 1

    def summary(self) -> str:
        reduction = (1 - self.chars_after / max(self.chars_before, 1)) * 100
        lines = [
            "",
            "  ┌─ RAPPORT DE NETTOYAGE ─────────────────────────────────────┐",
            f"  │  Documents traités          : {self.n_docs:>8,}              │",
            f"  │  Documents inchangés        : {self.docs_unchanged:>8,}"
            f"  ({self.docs_unchanged/max(self.n_docs,1)*100:.1f}%)  │",
            f"  │  Caractères avant           : {self.chars_before:>12,}          │",
            f"  │  Caractères après           : {self.chars_after:>12,}          │",
            f"  │  Réduction totale           : {reduction:>7.1f} %              │",
            f"  │  Suppressions bib       : {self.bib_hits:>8,}              │",
            "  │                                                             │",
            "  │  Segments d'exclusion — répartition par catégorie :        │",
        ]
        for cat, count in self.segments_hits.most_common():
            lines.append(f"  │    {cat:<30} : {count:>6,}                │")
        lines.append("  └─────────────────────────────────────────────────────────────┘")
        return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────
# NETTOYAGE INSTRUMENTÉ
# ──────────────────────────────────────────────────────────────────────

# Pré-compilation des patterns bib pour les compter
_LAM_PATTERNS_RE = [
    re.compile(p, re.IGNORECASE | re.MULTILINE) for p in BIB_PATTERNS
]
_LAM_TOKENS_RE = re.compile(
    r"(?<!\w)(" + "|".join(re.escape(t) for t in BIB_TOKENS) + r")(?!\w)",
    re.IGNORECASE,
)

# Segments d'exclusion : pré-compilation (insensible à la casse)
_SEG_RE: list[tuple[re.Pattern, str]] = [
    (re.compile(re.escape(seg), re.IGNORECASE), cat)
    for seg, cat in EXCLUSION_SEGMENTS
]


def clean_and_count(text: str) -> tuple[str, Counter, int]:
    """
    Nettoie le texte et retourne :
      (texte_propre, compteur_catégories_segments, nb_hits_bib)
    """
    seg_cats  = Counter()
    lam_count = 0

    # ── Couche 1 : segments d'exclusion ──────────────────────────────
    for pat, cat in _SEG_RE:
        new_text, n = pat.subn(" ", text)
        if n:
            seg_cats[cat] += n
            text = new_text

    # ── Couche 2a : patterns bib ─────────────────────────────────
    for pat in _LAM_PATTERNS_RE:
        new_text, n = pat.subn(" ", text)
        lam_count += n
        text = new_text

    # ── Couche 2b : tokens bib ────────────────────────────────────
    new_text, n = _LAM_TOKENS_RE.subn(" ", text)
    lam_count += n
    text = new_text

    # ── Normalisation finale ──────────────────────────────────────────
    text = re.sub(r"\s+", " ", text).strip()

    return text, seg_cats, lam_count


# ──────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────

def main():
    print("  SCRIPT 01bis — CONSTRUCTION DU CORPUS PROPRE (lexploreur)")
    print(f"  Couche 1 : {len(EXCLUSION_SEGMENTS)} segments d'exclusion")
    print(f"  Couche 2 : {len(BIB_PATTERNS)} patterns + "
          f"{len(BIB_TOKENS)} tokens bib")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── Si le JSON propre existe déjà ─────────────────────────────────
    if CORPUS_JSON.exists():
        print(f"\n  corpus_propre.json déjà présent : {CORPUS_JSON}")
        print("     Supprimez-le pour forcer la ré-annotation spaCy.")
        return

    # ── 1. Chargement des métadonnées ─────────────────────────────────
    print(f"\n── 1. Chargement des métadonnées ({META_CSV.name})")
    if not META_CSV.exists():
        print(f"  [ERREUR] Fichier introuvable : {META_CSV}")
        sys.exit(1)

    meta_df = pd.read_csv(META_CSV, encoding="utf-8-sig")
    print(f"  {len(meta_df):,} documents dans les métadonnées")

    for col in ("doc_id", "year"):
        if col not in meta_df.columns:
            print(f"  [ERREUR] Colonne manquante : '{col}'")
            sys.exit(1)

    # ── 2. Filtres ────────────────────────────────────────────────────
    print(f"\n── 2. Application des filtres")
    meta_df["year"] = pd.to_numeric(meta_df["year"], errors="coerce")

    before = len(meta_df)
    meta_df = meta_df.dropna(subset=["year"])
    print(f"  Supprimés (année manquante)     : {before - len(meta_df):,}")

    before = len(meta_df)
    meta_df = meta_df[
        (meta_df["year"] >= YEAR_MIN) & (meta_df["year"] <= YEAR_MAX)
    ]
    print(f"  Supprimés (hors {YEAR_MIN}-{YEAR_MAX})          : {before - len(meta_df):,}")

    before = len(meta_df)
    meta_df = meta_df[meta_df["doc_id"].astype(str) != EXCLUDE_ID]
    print(f"  Supprimés (id exclu)            : {before - len(meta_df):,}")

    meta_df["year"] = meta_df["year"].astype(int)
    print(f"  Documents retenus               : {len(meta_df):,}")

    # ── 3. Chargement + nettoyage des textes bruts ────────────────────
    print(f"\n── 3. Lecture, nettoyage, préparation du DataFrame")
    if not RAW_DIR.exists():
        print(f"  [ERREUR] Dossier raw_texts introuvable : {RAW_DIR}")
        sys.exit(1)

    report = CleaningReport()
    rows   = []
    missing = 0
    audit_shown = 0

    for _, row in tqdm(meta_df.iterrows(), total=len(meta_df),
                       desc="  Nettoyage"):
        doc_id   = str(row["doc_id"])
        raw_file = RAW_DIR / f"{doc_id}.txt"

        if not raw_file.exists():
            missing += 1
            continue

        raw_text = raw_file.read_text(encoding="utf-8", errors="replace")

        # ── Nettoyage avec comptage ───────────────────────────────────
        clean_text, seg_cats, lam_hits = clean_and_count(raw_text)
        report.add(doc_id, raw_text, clean_text, seg_cats, lam_hits)

        # ── Audit : aperçu avant/après sur un échantillon ────────────
        if AUDIT_SAMPLE > 0 and audit_shown < AUDIT_SAMPLE:
            if seg_cats or lam_hits:
                print(f"\n    ── AUDIT doc {doc_id} "
                      f"(seg={sum(seg_cats.values())}, lam={lam_hits}) ──")
                before_excerpt = raw_text[:300].replace("\n", " ")
                after_excerpt  = clean_text[:300].replace("\n", " ")
                print(f"    AVANT : {before_excerpt}")
                print(f"    APRÈS : {after_excerpt}")
                audit_shown += 1

        rows.append({
            "doc_id" : doc_id,
            "year"   : int(row["year"]),
            "title"  : row.get("title", ""),
            "texte"  : clean_text,
        })

    if missing:
        print(f"\n  [AVERTISSEMENT] {missing} fichiers .txt introuvables")

    print(report.summary())

    df = pd.DataFrame(rows)
    print(f"\n  DataFrame final : {len(df):,} documents nettoyés")

    if len(df) == 0:
        print("  [ERREUR] Aucun document à annoter.")
        sys.exit(1)

    # ── 4. Annotation spaCy → JSON lexploreur propre ──────────────────
    print(f"\n── 4. Annotation spaCy ({SPACY_MODEL}) → corpus_propre.json")
    print(f"  Sortie : {CORPUS_JSON}")
    print(f"  (Cette étape peut prendre plusieurs dizaines de minutes)\n")

    corpus(
        df,
        corpus_name = str(CORPUS_JSON),
        text_column = "texte",
        spacy_model = SPACY_MODEL,
        ner         = False,
    )

    print(f"\n  ✓ Corpus propre créé → {CORPUS_JSON.resolve()}")
    print(f"  Documents annotés : {len(df):,}")
    print(f"  Plage temporelle  : {df['year'].min()} – {df['year'].max()}")
    print("\n  Lancez maintenant : python 02bis_stats_corpus_propre.py")


if __name__ == "__main__":
    main()
