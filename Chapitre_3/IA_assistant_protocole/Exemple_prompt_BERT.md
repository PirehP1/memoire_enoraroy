# Prompt : Pipeline de topic modelling sur titres d'articles

> les commentaires que je fais sur ce prompt sont indiqués par ce style d'écriture

## Contexte

Je suis étudiante en master d'histoire - sciences des données. Dans le cadre de mon mémoire, j'ai constitué une base de données bibliographique de publications académiques en anglais sur le Haut Moyen Âge. Je dispose d'un corpus de 12 136 titres d'articles, prétraités avec SpaCy et exportés au format JSON. Je souhaite identifier les grandes thématiques disciplinaires présentes dans ce corpus afin d'en dresser une cartographie.

> ici, je conçois qu'indiquer le contexte n'était pas forcément nécessaire, puisque j'avais déjà une idée précise du workflow que je souhaitais suivre. Si je précise "en anglais", c'est parce que je souhaitais que BERT travaille uniquement sur les titres anglais, et j'ai donc exporté le json en conséquences (cela ne signifie pas que ma base n'a pas plus de titres !).

## Ressources disponibles

Le corpus est un fichier JSON structuré comme suit (extrait) :

```json
[
  {
    "document": {
      "_id": "ref_001",
      "lexical_features": [
        {"token": "Vikings", "lemma": "Viking"},
        {"token": "and",     "lemma": ""},
        {"token": "trade",   "lemma": ""}
      ]
    }
  }
]
```

> Il aurait aussi été possible de copier coller directement un extrait du json, voire même partir de ma base de données MongoDB ! Ne sachant pas initialement dans quelle mesure la lemmatisation était nécessaire, je préférais partir du corpus traité.

J'ai également un fichier `stop_words_english.txt` avec mes stopwords personnalisés, un mot par ligne.

## Objectif

Produis un script Python complet `bertopic_pipeline.py` qui :

1. Charge le JSON et prépare le corpus pour le topic modelling
2. Encode les titres avec un modèle de transformers MPNET (par défaut de BERT)
3. Réduit la dimensionnalité pour le clustering
4. Fais un sweep pour visualiser, par l'évolution de la cohérence, le nombre optimal de thématiques.
5. Ajuste le modèle BERTopic selon le nombre de topic sélectionné 
5. Affiche les termes les plus discriminants par thématique (c-tf-idf)
6. Exporte les résultats dans deux fichiers CSV :
   `document_topics.csv` (identifiant du document et topic assigné) et
   `topic_terms.csv` (termes caractéristiques par topic)

> étape par étape, car d'expérience, cela améliore considérablement les résultats que j'ai pu obtenir. En outre, cela m'aide sincèrement à formaliser le problème et la solution que j'envisage.
> remarque : cela suppose une connaissance préalable de BERT (lire la documentation, les articles sur le sujet etc)

## Contraintes

- Tous les paramètres configurables (chemins, seuils, nombre de topics) doivent être regroupés en haut du script
- Le script doit, autant que possible, réutiliser des outils existants (bibliothèques), sans classes ni fonctions utilitaires superflues
- Justifie brièvement dans les commentaires les choix méthodologiques structurants (modèle d'embedding, algorithme de clustering, méthode de sélection du nombre de topics)
