"""
Concordancier KWIC (Keywords In Context) sur corpus JSON.
note : il aurait été possible d'utiliser la fonction dédiée du paquet lexploreur
Pour un lemme donné, extrait toutes les occurrences avec leur contexte gauche
et droit (fenêtre configurable). Les résultats sont exportés en CSV et en LaTeX
dans un dossier de sortie.

Structure attendue du corpus JSON :
    [
      {
        "document": {
          "doc_id": "...",
          "year": "...",
          "title": "...",
          "lexical_features": [
            { "token": "...", "lemma": "...", "pos": "..." },
            ...
          ]
        }
      },
      ...
    ]

Note : pd.DataFrame.to_latex() est déprécié depuis pandas 2.0. Si cette
dépendance pose problème, envisager le package 'tabulate' en remplacement.

Usage :
    python kwic.py corpus_propre.json
    python kwic.py corpus_propre.json --window 10 --output concordances/
"""

import json
import re
import argparse
import pandas as pd
from pathlib import Path


def normalize(text: str) -> str:
    """
    Normalise les variantes typographiques avant comparaison :
    - tirets (en dash, em dash, figure dash, tiret insécable) → tiret ASCII
    - apostrophes typographiques → apostrophe droite ASCII
    - mise en minuscules

    Cela évite les faux négatifs lorsque le corpus contient des caractères
    Unicode qui ne matcheraient pas une saisie clavier standard.
    """
    text = text.replace("\u2013", "-")  # –  en dash
    text = text.replace("\u2014", "-")  # —  em dash
    text = text.replace("\u2012", "-")  # ‒  figure dash
    text = text.replace("\u2011", "-")  # ‑  tiret insécable
    text = text.replace("\u2019", "'")  # '  apostrophe typographique droite
    text = text.replace("\u2018", "'")  # '  apostrophe typographique gauche
    return text.lower()


# ==========================================================
# KWIC
# ==========================================================

def keywords_in_context(
    data: list, pivot: str, field: str = "lemma", window: int = 8
) -> pd.DataFrame:
    """
    Extrait toutes les occurrences du pivot dans le corpus avec leur contexte.

    Paramètres
    ----------
    data   : liste des entrées du corpus JSON
    pivot  : lemme (ou token) recherché
    field  : champ de lexical_features à comparer ("lemma" par défaut)
    window : nombre de tokens de contexte de chaque côté

    Retourne
    --------
    DataFrame avec colonnes : year, title, left, keyword, right
    """
    results = []
    pivot_norm = normalize(pivot)

    for item in data:
        doc    = item["document"]
        year   = doc.get("year", "")
        title  = doc.get("title", "")
        tokens = doc["lexical_features"]

        for i, tok in enumerate(tokens):
            if normalize(str(tok.get(field, ""))) == pivot_norm:

                # Fenêtre gauche : les `window` tokens précédant le pivot
                left  = tokens[max(0, i - window):i]
                # Fenêtre droite : les `window` tokens suivant le pivot
                right = tokens[i + 1:i + 1 + window]

                results.append({
                    "year":    year,
                    "title":   title,
                    "left":    " ".join(t["token"] for t in left),
                    "keyword": tok["token"],
                    "right":   " ".join(t["token"] for t in right),
                })

    return pd.DataFrame(results)


# ==========================================================
# EXPORT LATEX
# ==========================================================

def export_tex(df: pd.DataFrame, filepath: Path) -> None:
    """
    Exporte le DataFrame en tableau LaTeX (sans légende ni label).
    Le fichier produit peut être inclus directement via \\input{} dans LaTeX.
    """
    latex = df.to_latex(
        index=False,
        escape=True,
        longtable=False,
        caption=None,
        label=None,
    )
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(latex)


# ==========================================================
# PROGRAMME PRINCIPAL
# ==========================================================

def main():
    parser = argparse.ArgumentParser(
        description="Concordancier KWIC sur corpus JSON — export CSV et LaTeX."
    )
    parser.add_argument("corpus", help="Chemin vers le fichier corpus JSON.")
    parser.add_argument(
        "--window", type=int, default=8,
        help="Taille de la fenêtre de contexte de chaque côté du pivot (défaut : 8)."
    )
    parser.add_argument(
        "--output", default="concordances",
        help="Dossier de sortie pour les exports (défaut : concordances/)."
    )
    args = parser.parse_args()

    export_folder = Path(args.output)
    export_folder.mkdir(exist_ok=True)

    print("=" * 60)
    print("Chargement du corpus...")
    with open(args.corpus, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"{len(data)} documents chargés.\n")

    # Boucle interactive : l'utilisateur saisit un lemme à la fois
    while True:
        pivot = input("Entrez un lemme (ou EXIT) : ").strip()

        if pivot.lower() == "exit":
            print("Fin du programme.")
            break

        df = keywords_in_context(data, pivot=pivot, field="lemma", window=args.window)

        if df.empty:
            print("Aucune occurrence trouvée.\n")
            continue

        print(f"\n{len(df)} occurrence(s) trouvée(s)\n")

        # Aperçu console des 20 premières lignes
        for _, row in df.head(20).iterrows():
            print(f"[{row['year']}] {row['left']} >>> {row['keyword']} <<< {row['right']}")

        # Construction du nom de fichier (nettoyage des caractères interdits)
        safe = re.sub(r'[\\/:*?"<>|]', "_", pivot).replace(" ", "_").lower()
        csv_file = export_folder / f"concordances_{safe}.csv"
        tex_file = export_folder / f"concordances_{safe}.tex"

        df.to_csv(csv_file, index=False, encoding="utf-8-sig")
        export_tex(df, tex_file)

        print(f"\nFichiers exportés :\n  {csv_file}\n  {tex_file}\n")


if __name__ == "__main__":
    main()
