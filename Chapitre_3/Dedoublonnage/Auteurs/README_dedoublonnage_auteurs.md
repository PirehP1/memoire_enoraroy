## Dossier `auteurs/`
Un auteur peut apparaître plusieurs fois dans la base sous des graphies différentes : translittération variable depuis un alphabet non latin, inversion nom/prénom, présence ou absence d'initiales, légère variation orthographique. Aucun de ces cas ne peut être détecté par un simple test d'égalité stricte entre les chaînes de caractères. Les scripts de détection couvrent chacun un type de doublon distinct et sont complémentaires, leurs résultats étant des fichiers JSON indépendants à vérifier manuellement avant application.

### Scripts de détection

**`A_dedoublonnage_auteurs_nomexact.py`** — Correspondance exacte du `NomComplet` normalisé (minuscules, sans diacritiques, sans ponctuation). Cas le plus simple : même nom encodé différemment (espaces, casse, accents).

**`B_dedoublonnage_auteurs_initiale.py`** — Détecte les paires partageant le même nom de famille (`Nom`) et dont le prénom de l'un est une initiale du prénom de l'autre (ex. : *Dupont J.* vs *Dupont Jean*), ainsi que les paires dont le `NomComplet` normalisé présente un ratio Levenshtein ≥ 0,85.

**`C_dedoublonnage_auteurs_inversion.py`** — Détecte les inversions nom/prénom (*Dupont, Jean* vs *Jean Dupont*) en triant les tokens du nom avant comparaison. Une signature minimale (tokens de longueur > 1) sert de clé de blocage, et une signature complète (tous les tokens triés) est soumise à Levenshtein.

**`D_dedoublonnage_auteurs_translitteration.py`** — Cible les auteurs dont le nom est écrit dans un alphabet non latin (cyrillique, grec, arabe, hébreu, arménien, géorgien). Le nom est translittéré vers le latin avant comparaison Levenshtein. Seules les paires où au moins un nom est non latin sont retenues, de sorte à ne pas faire doublon avec les scripts purement latins.

### Sortie
Chaque script de détection produit un fichier JSON listant les clusters de doublons potentiels, avec pour chaque auteur ses publications liées et une suggestion d'action (`keep` / `delete` / `skip`). **Ces fichiers peuvent être donc vérifiés vérifier manuellement avant toute application.**

### Scripts d'application

**`E_appliquer_dedoublonnage_auteurs.py`** — Lit les fichiers JSON produits par les scripts de détection (après vérification manuelle) et applique les fusions en base. Opérations effectuées pour chaque auteur supprimé :
  1. Redirection dans la table `ecriture` : les lignes pointant vers l'auteur
     supprimé sont redirigées vers l'auteur conservé.
     Les doublons éventuels dans `ecriture` (même reference_id + même author_id)
     sont supprimés plutôt que mis à jour, pour éviter les violations de contrainte.
  2. Suppression de l'auteur dans la table `authors`.

**`F_dedoublonnage_auteurs_par_identifiants.py`** — Détecte et fusionne les doublons partageant un identifiant commun (`PPN_IDREF`, `PPN_VIAF`, etc.). Transfère les identifiants manquants vers l'auteur conservé, redirige les liens de la table `ecriture`, supprime les doublons.
