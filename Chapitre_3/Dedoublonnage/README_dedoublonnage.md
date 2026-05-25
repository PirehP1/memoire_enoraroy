# Déduplication des auteurs et des références bibliographiques

Ce dossier regroupe les scripts utilisés pour le dédoublonnage de ma base de données MySQL. Si ces scripts permettent une semi-automatisation du process, je tiens à rappeler qu'une petite partie de ces doublons a été enlevée manuellement (dont je n'ai malheureusement pas compté le nombre d'occurrences, suffisamment peu pour qu'on ne les compte pas).

Le dossier `references/` contient les scripts utilisés pour dédoublonner les références de notre base selon des critères progressivement moins stricts : doi, issn, puis titre et titre secondaire. J'explique la démarche dans un README dans le dossier.

Le dossier `auteurs/` contient les scripts utilisés pour dédoublonner les auteurs : une réserve s'impose toutefois, liée à l'onomastique. En ce sens, je recommande vivement de dédoublonner d'abord les références, puis supprimer les auteurs n'ayant plus aucun lien, avant de dédoublonner les auteurs de manière supervisée. Ces scripts ont permis de dédoublonner les auteurs en prévoyant la similarité entre les noms et les prénoms, les cas d'inversion, et d'initiales utilisées (par exemple, W. Pohl pour Walter Pohl).

Enfin, le dossier `intervalle_confiance/` contient les scripts python et R utilisés pour calculer un intervalle pour évaluer la qualité de notre protocole.

Si une automatisation totale aurait été moins chronophage, je souhaitais conserver un contrôle, du moins partiel, sur mes données, en voyant clairement ce qui allait être fusionné -- d'où des programmes en deux étapes, d'abord un regroupement, puis une application. Ci-dessous, je détaille chaque dossier : les programmes sont numérotés dans leur ordre d'exécution préférable, mais il n'est pas impossible de ne pas le respecter.

> NOTE : J'ai itéré le processus plus d'une fois, ce qui implique que les seuils retenus pour la distance de Levenshtein pour la comparaison de chaînes de caractère n'est pas nécessairement à suivre. Il s'agit en ce sens d'une valeur indicative plutôt qu'absolue : je recommande d'aller du plus strict, pour éliminer les vrais doublons, au plus souple. Un seuil trop bas génère des faux positifs (auteurs ou références distincts regroupés à tort) ; un seuil trop haut laisse passer des vrais doublons.

---

## Dépendances

```
pip install mysql-connector-python python-Levenshtein transliterate translit-me
```
