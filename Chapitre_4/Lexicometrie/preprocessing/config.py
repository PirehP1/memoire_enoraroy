# config.py
# ──────────────────────────────────────────────────────────────────────
# Chemins partagés par tous les scripts du dossier preprocessing/.
# Ce fichier est le seul à modifier si le projet est déplacé.
# ──────────────────────────────────────────────────────────────────────
import pathlib

_HERE = pathlib.Path(__file__).resolve().parent   # preprocessing/
_ROOT = _HERE.parent                               # racine du dépôt

CORPUS_JSON   = _ROOT / "output" / "corpus_propre" / "corpus_propre.json"
RAW_TEXTS_DIR = _ROOT / "raw_texts"
