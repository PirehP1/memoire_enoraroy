"""
01_load_corpus.py — Chargement du JSON SpaCy et construction des deux corpus.

Deux versions du corpus sont construites :
  docs        = tokens originaux (minuscules, alpha uniquement)
                Destiné à l'encodage BERT. Les transformeurs gèrent nativement
                la morphologie via BPE (Reimers & Gurevych, 2019).
  docs_ctfidf = lemme SpaCy si disponible (entités nommées reconnues),
                sinon token original (minuscule).
                Destiné au CountVectorizer / c-TF-IDF uniquement.
                Le champ "lemma" dans le JSON n'est renseigné que pour les
                entités nommées (POS non vide) ; pour les tokens communs,
                "lemma" est une chaîne vide (t.get("lemma") → falsy).

Avoir les deux permet d'alterner entre une lecture des topics des clusters
et un corpus adapté à BERTopic.

Outputs : docs_cache2.npy, docs_ctfidf_cache2.npy, doc_ids_cache2.npy
"""

import json
import numpy as np
from config import *

with open(INPUT_JSON, "r", encoding="utf-8") as f:
    data_json = json.load(f)

cache_ok = (
    os.path.exists(DOCS_CACHE) and
    os.path.exists(IDS_CACHE) and
    os.path.exists(DOCS_CTFIDF_CACHE)
)

if cache_ok:
    print("Docs trouvés en cache → chargement...")
    docs        = list(np.load(DOCS_CACHE,        allow_pickle=True))
    doc_ids     = list(np.load(IDS_CACHE,         allow_pickle=True))
    docs_ctfidf = list(np.load(DOCS_CTFIDF_CACHE, allow_pickle=True))
else:
    print("Construction des corpus (tokens + c-TF-IDF)...")
    docs, docs_ctfidf, doc_ids = [], [], []

    for item in data_json:
        lexical = item.get("document", {}).get("lexical_features", [])

        # Version BERT : tokens originaux, filtre alpha uniquement
        tokens = [
            t["token"].lower()
            for t in lexical
            if t.get("token", "").isalpha()
        ]

        # Version c-TF-IDF : lemme si disponible, sinon token
        tokens_ctfidf = [
            (t.get("lemma") or t["token"]).lower()
            for t in lexical
            if t.get("token", "").isalpha()
        ]

        docs.append(" ".join(tokens))
        docs_ctfidf.append(" ".join(tokens_ctfidf))
        doc_ids.append(item.get("document", {}).get("_id", ""))

    np.save(DOCS_CACHE,        np.array(docs,        dtype=object))
    np.save(DOCS_CTFIDF_CACHE, np.array(docs_ctfidf, dtype=object))
    np.save(IDS_CACHE,         np.array(doc_ids,     dtype=object))
    print("Corpus sauvegardés en cache.")

print(f"Documents chargés : {len(docs)}")
