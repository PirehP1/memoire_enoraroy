# Pipeline d'imputation du genre des auteurs

Ce dossier regroupe les scripts utilisés pour enrichir la base de données MongoDB locale avec le genre imputé des auteurs (`genre_impute`). La pipeline repose sur une double validation : une première prédiction par [NamSor](https://namsor.fr/) (API d'onomastique), suivie d'une vérification par un LLM ([Mistral](https://mistral.ai/fr/products/studio/)). Seuls les accords entre les deux systèmes sont injectés automatiquement ; les conflits sont isolés pour arbitrage manuel. Les fichiers intermédiaires sont au format JSONL. Ce workflow s'inspire notamment de l'article de Goyanes et al., disponible [ici](https://link.springer.com/10.1007/s11192-024-05149-2).

> Goyanes, M., de-Marcos, L., & Domínguez-Díaz, A. (2024). Automatic gender detection: a methodological procedure and recommendations to computationally infer the gender from names with ChatGPT and gender APIs. *Scientometrics*, *129*, 6867–6888. [https://doi.org/10.1007/s11192-024-05149-2](https://doi.org/10.1007/s11192-024-05149-2)

Les scripts sont numérotés dans leur ordre d'exécution. `01` et `02` peuvent être exécutés indépendamment (deux stratégies NamSor distinctes), mais tous deux doivent précéder `03`, qui doit lui-même précéder `04`.

---

Fichiers de sortie principaux :

| Fichier | Produit par | Utilisé par |
|---|---|---|
| `auteurs_genres.jsonl` | 01 | 03 |
| `auteurs_genre_impute_vsansnat.jsonl` | 02 | 03 |
| `auteurs_genre_verifie_llm.jsonl` | 03 | 04 |
| `conflicts_genre_llm.jsonl` | 03 | 04 (après arbitrage manuel) |

---

## Description des scripts

### `01_genre_auteur_via_nationalite.py` — Prédiction NamSor avec contexte géographique

Charge depuis MongoDB les auteurs sans genre renseigné et disposant d'au moins une nationalité. Pour chaque auteur, interroge l'endpoint `genderFullGeoBatch` de NamSor en transmettant le nom complet et le code ISO 2 du pays de nationalité : la géolocalisation améliore la précision de la prédiction pour les prénoms dont le genre varie selon la culture. Les codes ISO sont récupérés via l'API Wikidata et mis en cache localement (`iso_cache.json`) pour éviter les appels redondants. Les résultats sont écrits ligne par ligne dans `auteurs_genres.jsonl`  ; un fichier de progression (`progress.json`) permet la reprise sans perte en cas d'interruption.

> Note : la validation des noms écarte les initiales seules et les formats trop abrégés, qui produiraient des prédictions peu fiables.

Sorties : `auteurs_genres.jsonl`, `progress.json`, `iso_cache.json`.

---

### `02_genre_auteur_sans_nationalite.py` — Prédiction NamSor sans contexte géographique

Variante du script `01` pour les auteurs sans nationalité renseignée en base. Interroge l'endpoint `genderFullBatch` de NamSor (sans géolocalisation). La logique de validation des noms est identique : les noms composés uniquement d'initiales ou trop courts sont écartés et consignés dans le fichier de sortie avec `"traitable": false`, pour traçabilité. La reprise est gérée par lecture du fichier de sortie existant au démarrage.

Sorties : `auteurs_genre_impute_vsansnat.jsonl`.

---

### `03_verifier_genre_avec_Mistral.py` — Vérification des prédictions NamSor par LLM

Lit les fichiers produits par `01` et/ou `02` et soumet chaque nom à Mistral (`mistral-small-latest`) pour un second avis indépendant. La prédiction est obtenue par un prompt d'onomastique à réponse contrainte (0 / 1 / 2), avec `temperature=0` pour maximiser le déterminisme. Les cas sont ensuite répartis selon l'accord entre les deux systèmes :

- **Accord NamSor = LLM** → ligne écrite dans `auteurs_genre_verifie_llm.jsonl` avec `genre_final` renseigné.
- **Désaccord** → ligne écrite dans `conflicts_genre_llm.jsonl` avec `genre_final: null`.

La reprise est automatique : les auteurs déjà présents dans l'un ou l'autre fichier de sortie sont ignorés au démarrage. Un résumé (accords / conflits / échecs API, répartition par genre) est affiché en fin d'exécution.

> Note : `NAMSOR_CONFIDENCE_THRESHOLD` (par défaut `1.0`) permet de restreindre la vérification LLM aux prédictions NamSor sous un certain seuil de confiance. À `1.0`, tous les auteurs traitables sont vérifiés.

Sorties : `auteurs_genre_verifie_llm.jsonl`, `conflicts_genre_llm.jsonl`.

---

### `04_insertion_genre_impute_bdd.py` — Insertion en base MongoDB

Lit les deux fichiers produits par `03` et met à jour le champ `genre_impute` de la collection `authors` dans MongoDB. Propose un menu interactif à quatre options :

1. **Dry run accords** — simule l'insertion des accords sans écrire en base.
2. **Insérer accords** — insère les accords NamSor + LLM (`source: "both_agree"`).
3. **Insérer conflits arbitrés manuellement** — insère les conflits dont `genre_final` a été renseigné à la main dans `conflicts_genre_llm.jsonl` (`source: "arbitrage_manuel"`). Les entrées encore à `null` sont ignorées.
4. **Stats MongoDB** — affiche la distribution des champs `genre.valeur` et `genre_impute.valeur` en base.

**Arbitrage manuel (étape intermédiaire avant l'option 3)** : ouvrir `conflicts_genre_llm.jsonl` et, pour chaque ligne à trancher, remplacer `"genre_final": null` par `"male"` ou `"female"` et `"source"` par `"arbitrage_manuel"`. Les entrées non modifiées restent ignorées.

Règle : si le LLM a répondu `unknown` et qu'aucun arbitrage manuel n'a été fourni, le document n'est pas inséré.

La structure insérée en base est la suivante :

```json
"genre_impute": {
  "valeur": "male",
  "source": "both_agree",
  "date_imputation": { "$date": "..." },
  "methode": "namsor_llm_verification",
  "details": {
    "namsor_gender": "male",
    "llm_gender": "male",
    "probabilite_namsor": 0.647,
    "note": null
  }
}
```

Sorties : mise à jour en base (aucun fichier produit).

---

## Note méthodologique

NamSor est plus fiable sur les prénoms complets que sur les initiales, et plus précis avec un contexte géographique. La double validation NamSor + LLM réduit le taux d'imputation erronée mais ne l'élimine pas : les prénoms androgynes ou très rares restent sources d'erreur dans les deux systèmes. Le taux de conflits observé constitue un indicateur indirect de la difficulté onomastique du corpus. En outre, l'expérience nous a permis de constater que Mistral a bien souvent davantage raison que Namsor, en plus d'être plus accessibles en termes de prix puisque les limites de gratuité y sont plus strictes.

---

## Dépendances

```
pip install pymongo python-Levenshtein requests mistralai
```

Une instance MongoDB locale est requise pour `01`, `02` et `04`. Le script `03` interroge l'API Mistral ; une connexion internet est nécessaire. Les clés API NamSor et Mistral sont à renseigner dans les constantes de configuration en tête de chaque script.
