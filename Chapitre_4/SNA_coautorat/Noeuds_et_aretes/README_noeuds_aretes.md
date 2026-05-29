# Données Graphes — Noeuds et Arêtes (SNA)

Ce dossier regroupe les fichiers de structure du réseau (noeuds et arêtes) directement extraits et construits à partir de la base de données MongoDB `references_biblio` (collections `authors` et `references`).  Ces fichiers servent de base aux calculs des métriques de centralité et aux visualisations de réseaux.

---

### 1. Le Fichier des Noeuds (`nodes_all.csv`)

Ce fichier contient **l'ensemble des entités (sommets)** du réseau avant filtrage ou calculs avancés. Il fusionne les données d'identification issues de MongoDB.

* **Contenu :** Il liste tous les acteurs du réseau, à savoir :
  * Les **Auteurs** (extraits de la collection `authors`), identifiés par leur clé unique (`Nom, Prenom_Timestamp`).
  * Les **Publications** (extraites de la collection `references`), identifiées par leur identifiant unique MongoDB (`_id` / `$oid`).
  
---

### 2. Le Fichier des Arêtes (`edges_author_pub.csv`)

Ce fichier formalise **les relations (liens)** qui unissent les entités du réseau. 

* **Structure de réseau biparti (Auteur-Publication) :** Il matérialise le fait qu'un auteur a contribué à une publication.
* **Format des colonnes :**
  * `source` : L'identifiant unique de l'auteur (ou de la publication).
  * `target` : L'identifiant unique de la publication associée (ou de l'auteur).
* **Utilité :** C'est ce fichier de liens qui permet de générer, par projection, soit le réseau de **co-autorat** (auteurs connectés s'ils ont écrit ensemble), soit le réseau des **publications** (liées par des co-auteurs ou des thématiques communes).

---

> NOTE : systématiquement, les noeuds sont enrichis avec des attributs de nos données sur MongoDB (langue, nationalité, genre)
