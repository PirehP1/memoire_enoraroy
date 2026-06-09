#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Conversion de fichiers CSV KWIC au format corpus IRaMuTeQ.
à exécuter après avoir extrait les concordances à l'aide du premier script 
Lit tous les fichiers concordances_*.csv d'un dossier source et génère
pour chacun un fichier texte compatible IRaMuTeQ, où chaque segment
correspond à une ligne KWIC (contexte gauche + mot pivot + contexte droit).

Format de sortie IRaMuTeQ :
    **** *YEAR_<année> *DOC_<titre_tronqué>
    <contexte gauche> <mot pivot> <contexte droit>

    (ligne vide entre deux segments)

Usage :
    python kwic_to_iramuteq.py
    python kwic_to_iramuteq.py --input concordances/ --output iramuteq/
"""

import argparse
import pandas as pd
from pathlib import Path


# ==========================================================
# NETTOYAGE
# ==========================================================

def clean(text) -> str:
    """
    Normalise une cellule CSV pour IRaMuTeQ :
    - remplace les sauts de ligne et tabulations par des espaces
    - supprime les espaces en début et fin
    - retourne une chaîne vide si la valeur est NaN
    """
    if pd.isna(text):
        return ""
    return (
        str(text)
        .replace("\n", " ")
        .replace("\r", " ")
        .replace("\t", " ")
        .strip()
    )


# ==========================================================
# CONVERSION D'UN FICHIER
# ==========================================================

def csv_to_iramuteq_corpus(csv_path: Path, output_path: Path) -> None:
    """
    Convertit un CSV KWIC en corpus texte pour IRaMuTeQ.

    Colonnes attendues dans le CSV : year, title, left, keyword, right.
    Les lignes dont les trois champs de contexte sont vides sont ignorées.

    Contrainte IRaMuTeQ : les espaces dans les variables de l'en-tête sont
    interdits. Le titre est donc remplacé par des underscores et tronqué
    à 50 caractères.
    """
    df = pd.read_csv(csv_path, encoding="utf-8")

    required = {"year", "title", "left", "keyword", "right"}
    if not required.issubset(df.columns):
        raise ValueError(
            f"Colonnes manquantes dans {csv_path.name}. "
            f"Attendu : {required} — Trouvé : {set(df.columns)}"
        )

    with open(output_path, "w", encoding="utf-8") as f:
        for _, row in df.iterrows():
            left    = clean(row["left"])
            keyword = clean(row["keyword"])
            right   = clean(row["right"])

            # Ignorer les lignes entièrement vides
            if not any([left, keyword, right]):
                continue

            year      = clean(row["year"])
            # IRaMuTeQ n'accepte pas les espaces dans les variables étoilées
            title_var = clean(row["title"]).replace(" ", "_")[:50]

            # En-tête de segment IRaMuTeQ
            f.write(f"**** *YEAR_{year} *DOC_{title_var}\n")

            # Segment = reconstitution du contexte KWIC sur une seule ligne
            f.write(f"{left} {keyword} {right}".strip() + "\n\n")


# ==========================================================
# TRAITEMENT EN LOT
# ==========================================================

def convert_all(input_folder: Path, output_folder: Path) -> None:
    """
    Convertit tous les fichiers concordances_*.csv du dossier source.
    Un fichier iramuteq_corpus_<lemme>.txt est produit pour chacun.
    """
    output_folder.mkdir(parents=True, exist_ok=True)
    files = sorted(input_folder.glob("concordances_*.csv"))

    if not files:
        print(f"Aucun fichier CSV trouvé dans {input_folder}/")
        return

    for file in files:
        name        = file.stem.replace("concordances_", "")
        output_file = output_folder / f"iramuteq_corpus_{name}.txt"
        print(f"  {file.name} → {output_file.name}")
        csv_to_iramuteq_corpus(file, output_file)

    print(f"\n✔ {len(files)} corpus IRaMuTeQ générés dans {output_folder}/")


# ==========================================================
# POINT D'ENTRÉE
# ==========================================================

def main():
    parser = argparse.ArgumentParser(
        description="Convertit des CSV KWIC en corpus texte pour IRaMuTeQ."
    )
    parser.add_argument(
        "--input", default="concordances",
        help="Dossier source contenant les CSV KWIC (défaut : concordances/)."
    )
    parser.add_argument(
        "--output", default="concordances",
        help="Dossier de sortie pour les corpus IRaMuTeQ (défaut : concordances/)."
    )
    args = parser.parse_args()

    convert_all(Path(args.input), Path(args.output))


if __name__ == "__main__":
    main()
