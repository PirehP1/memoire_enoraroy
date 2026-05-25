## Dossier `intervalle_confiance/`

Afin de valider la qualité du travail de dédoublonnage, je propose un script (`calcul_plot_IC.R`) pour extraire les données de trois bases MySQL différentes pour vérifier que les décisions prises au cours du dédoublonnage soient comprises entre les données d'origine, et les données dédoublonnées automatiquement.

Faute de vérité terrain absolue, la valeur idéale attendue peut être définie comme le juste milieu physique entre la base brute (`non_dedoublonne`) et la base nettoyée au maximum par algorithme (`sans_doublon`).
Les seuils de tolérance (Intervalle de confiance) : Le script dresse des limites autour de la moyenne estimée :
   * Une zone de confiance standard à **95%** (marge de +/- 1,96 écart-type).
   * Une zone de confiance élargie à **99%** (marge de +/- 2,576 écart-types).

### Dédoublonnage algorithmique strict (Génération de la borne minimale)

Ce script Python réalise un dédoublonnage entièrement automatisé et volontairement strict sur la base de données brute issue des exports RIS de WorldCat. Son objectif principal n'est pas de remplacer le travail de révision humaine, mais de créer une base de données de référence `biblio_sans_doublon`. Cette base sert de borne minimale (le scénario du "zéro doublon") indispensable au calcul de l'intervalle de confiance permettant de valider nos stratégies de dédoublonnage. Le dédoublonnage manuel est, en ce sens, considéré comme plutôt fiable s'il se situe entre la base brute (plafond maximal) et cette base nettoyée (plancher minimal). 
Le script crée la base `biblio_sans_doublon` si elle n'existe pas en clonant la structure de la table reference d'origine. Il extrait les données de la base brute (Via une jointure globale (`LEFT JOIN`), il récupère les titres secondaires (`secondary_title`) corrigés dans la base de travail manuel, afin d'éviter que des variations de saisie sur les noms de revues ou d'éditeurs ne bloquent la détection des doublons).
Chaque notice subit un nettoyage textuel profond via la fonction `clean_text`, comme nous l'avons fait pour nos pratiques de dédoublonnage:
* Retrait de toutes les balises HTML et résidus d'encodage (ex: `<em>`, `<i>`, `&#...;`).
* Suppression complète des accents.
* Remplacement de toute la ponctuation par des espaces et passage en minuscules.
* Tri des notices par longueur de titre (du plus court au plus long) pour optimiser les comparaisons de chaînes.

Enfin, les notices sont dédoublonnées selon un seuil de $\ge 90$ pour le titre et le titre secondaire, et l'année de publication doit être exactement égale.
