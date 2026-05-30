"""
bnf_match.py
────────────
Résolution des notices d'autorité de personnes physiques par appariement
entre une base MySQL locale et les fichiers d'autorité de la BnF
(format ISO 2709 / UNIMARC, produits rétrospectifs du Catalogue général).

Principe
--------
Les auteurs de la base sont chargés en mémoire et indexés par tokens de
noms. Les fichiers BnF sont ensuite lus en flux (chunk par chunk) : pour
chaque notice de personne rencontrée, seuls les auteurs partageant au
moins MIN_SHARED_TOKENS tokens avec elle sont soumis au calcul de score.
Cela évite d'exécuter des millions de comparaisons Levenshtein inutiles.

Critères de validation d'un match
----------------------------------
Un appariement n'est retenu que si :
  1. La notice BnF contient au moins une œuvre citée (champ 810) ;
  2. L'auteur local possède au moins un titre associé dans la base ;
  3. Les deux titres retenus font chacun ≥ 15 caractères normalisés
     (filtrage des titres de revues, mots isolés, etc.) ;
  4. Le meilleur score de similarité titre ≥ THRESHOLD_TITLE ;
  5. Le score combiné (60 % nom + 40 % titre) ≥ THRESHOLD_COMBINED.

Sortie
------
Fichier JSONL bnf_candidates.jsonl, une ligne par auteur :
  {"author_id": …, "name": …, "match": {…} | null}
Le champ "match" inclut l'identifiant BnF, le nom retenu, le score
combiné et le couple de titres ayant fondé l'appariement.

Reprise
-------
Les auteurs déjà présents dans le fichier de sortie sont ignorés,
ce qui permet de relancer le script sans écraser les résultats.

Dépendances : mysql-connector-python, python-Levenshtein, tqdm

Note : ce script est long, et a largement été fait par Claude. J'avais essayé d'utiliser pyunimarc, sans grand succès. Et étant donné mon faible usage des données de la BNF, je n'ai pas pris davantage de temps à ce propos.
"""

import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

import Levenshtein
import mysql.connector
from tqdm import tqdm


# ── Configuration ─────────────────────────────────────────────────────

# Paramètres de connexion à la base MySQL locale
MYSQL_CONFIG = {
    "host":     "localhost",
    "user":     "root",
    "password": "SQL2025Enora",
    "database": "test_programme",
}

BNF_DATA_DIR = "data_bnf"        # Dossier contenant les fichiers ISO 2709
OUTPUT_FILE  = "bnf_candidates.jsonl"
BNF_ENCODING = "utf-8"           # Encodage des fichiers BnF (alt. : "latin-1")
CHUNK_SIZE   = 1 << 16           # Taille des chunks de lecture : 65 536 octets (64 Ko)
                                  # Lire par morceaux évite de charger un fichier
                                  # de plusieurs Go entier en mémoire d'un coup.

# ── Délimiteurs du format ISO 2709 ───────────────────────────────────
# ISO 2709 est un format binaire/texte standardisé pour les notices bibliographiques.
# Chaque enregistrement se termine par le caractère ASCII 0x1D (GS, Group Separator).
# Les sous-champs à l'intérieur d'un champ sont séparés par 0x1F (US, Unit Separator),
# suivi immédiatement du code de sous-champ (une lettre, ex. "a", "b", "f").
RECORD_END      = "\x1d"         # Fin d'enregistrement (ASCII 29)
SUBFIELD_DELIM  = "\x1f"         # Séparateur de sous-champ (ASCII 31)

# ── Seuils de validation des appariements ────────────────────────────
# Ces valeurs contrôlent la rigueur du matching : les augmenter réduit
# les faux positifs mais augmente les faux négatifs (auteurs manqués).
THRESHOLD_COMBINED   = 0.82  # Score combiné minimum (60 % nom + 40 % titre)
THRESHOLD_TITLE      = 0.70  # Score de similarité titre minimum
MIN_TITLE_LENGTH     = 15    # Longueur normalisée minimale d'un titre exploitable
                              # (filtre les titres de revues, numéros isolés, etc.)
MIN_NAME_SCORE       = 0.65  # Pré-filtre : on abandonne si le score de nom est trop bas,
                              # sans même calculer la similarité des titres
MIN_SHARED_TOKENS    = 2     # Nombre minimum de tokens en commun entre un auteur local
                              # et une notice BnF pour que la paire soit évaluée


# ── Normalisation et similarité ───────────────────────────────────────

def normalize(text: str) -> str:
    """
    Normalise une chaîne pour la comparaison : mise en minuscules,
    suppression des diacritiques, de la ponctuation et des espaces multiples.

    Exemple : "Müller, Hans-Georg" → "muller hansgeorg"
    Cette normalisation garantit que les comparaisons ne sont pas
    pénalisées par des différences d'accentuation ou de casse entre
    les notices BnF et les noms de la base locale.
    """
    if not isinstance(text, str) or not text:
        return ""
    # NFKD décompose les caractères accentués en lettre de base + diacritique.
    # encode("ascii", "ignore") supprime ensuite les diacritiques détachés.
    text = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    # On remplace tout ce qui n'est pas une lettre, un chiffre ou un espace par un espace,
    # puis on compresse les espaces multiples.
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", text)).strip()


def tokenize(text: str) -> set[str]:
    """
    Retourne les tokens significatifs (longueur > 2) d'un texte normalisé.

    Les tokens de 1 ou 2 caractères (particules, initiales, etc.) sont
    exclus car trop peu discriminants pour l'index inversé.
    Exemple : "de la fontaine jean" → {"fontaine", "jean"}
    """
    return {t for t in normalize(text).split() if len(t) > 2}


def similarity(a: str, b: str) -> float:
    """
    Similarité de Levenshtein normalisée entre deux chaînes (0.0 → 1.0).

    La distance de Levenshtein compte le nombre minimal d'insertions,
    suppressions et substitutions pour passer d'une chaîne à l'autre.
    Levenshtein.ratio() normalise cette distance par la longueur totale
    des deux chaînes, produisant un score entre 0 (aucune ressemblance)
    et 1 (chaînes identiques).

    Optimisation : pour les chaînes longues (> 30 car.), un test de
    containment préalable évite le calcul Levenshtein quand l'une des
    chaînes est clairement incluse dans l'autre (ex. : titre avec/sans
    sous-titre).
    """
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return 0.0
    # Cas rapide : si l'une est incluse dans l'autre pour de longs textes, score = 1
    if len(na) > 30 and len(nb) > 30 and (na in nb or nb in na):
        return 1.0
    return Levenshtein.ratio(na, nb)


# ── Parseur ISO 2709 / UNIMARC ────────────────────────────────────────

def iter_records(filepath: str):
    """
    Génère les enregistrements ISO 2709 bruts d'un fichier, un par un,
    par lecture en chunks pour ne pas charger le fichier en mémoire.

    Stratégie : on lit le fichier par blocs de CHUNK_SIZE octets et on
    accumule les données dans un buffer. Chaque fois que le délimiteur
    de fin d'enregistrement (\\x1d) est trouvé dans le buffer, on extrait
    l'enregistrement complet et on le yield. Le fragment restant (début
    du prochain enregistrement, non encore terminé) est conservé dans
    le buffer pour le prochain chunk.
    """
    size = Path(filepath).stat().st_size
    # Barre de progression en octets pour surveiller l'avancement sur
    # des fichiers qui peuvent dépasser plusieurs centaines de Mo
    progress = tqdm(total=size, unit="B", unit_scale=True,
                    desc=Path(filepath).name, dynamic_ncols=True)
    buf = ""
    with open(filepath, encoding=BNF_ENCODING, errors="replace") as f:
        # errors="replace" : les caractères illisibles sont remplacés par U+FFFD
        # plutôt que de lever une exception — essentiel pour la robustesse
        # face aux notices dont l'encodage est corrompu ou inattendu.
        while chunk := f.read(CHUNK_SIZE):
            progress.update(len(chunk.encode(BNF_ENCODING, errors="replace")))
            buf += chunk
            # On coupe le buffer à chaque fin d'enregistrement
            parts = buf.split(RECORD_END)
            # Le dernier élément est le fragment incomplet du prochain enregistrement
            buf = parts.pop()
            for raw in parts:
                # On ignore les fragments trop courts pour être un enregistrement valide
                # (le leader seul fait déjà 24 caractères)
                if len(raw.strip()) >= 24:
                    yield raw.strip()
    progress.close()
    # Traitement du dernier enregistrement (pas de \x1d final dans certains fichiers)
    if len(buf.strip()) >= 24:
        yield buf.strip()


def parse_record(raw: str) -> dict[str, list[str]]:
    """
    Parse un enregistrement ISO 2709 brut et retourne un dictionnaire
    { tag_UNIMARC : [données_du_champ, …] }.

    Structure d'un enregistrement ISO 2709 :
    ┌─────────────────────────────────────────────────────────┐
    │ Leader (24 car.)  │ Répertoire (n × 12 car.) │ Données  │
    └─────────────────────────────────────────────────────────┘

    - Leader : métadonnées de l'enregistrement. Les positions 12–16
      contiennent l'adresse de base (offset en octets du début des données).
    - Répertoire : une liste d'entrées de 12 caractères chacune :
        * 3 car. = tag du champ (ex. "200", "810")
        * 4 car. = longueur du champ en octets (incluant le \x1e final)
        * 5 car. = position de début du champ dans la zone de données
      Le répertoire se termine quand on atteint l'adresse de base.
    - Données : les champs eux-mêmes, concaténés, chacun se terminant
      par \x1e (Field Terminator, ASCII 30).
    """
    try:
        # L'adresse de base indique où commencent les données dans l'enregistrement
        base = int(raw[12:17])
    except ValueError:
        # Enregistrement malformé : on retourne un dictionnaire vide
        return {}

    fields: dict[str, list[str]] = {}
    # Le répertoire occupe les positions 24 à (base - 1), par entrées de 12 car.
    # On s'arrête à base - 25 pour ne pas dépasser (le -1 est le terminateur de répertoire).
    for i in range(0, base - 25, 12):
        entry = raw[24 + i: 24 + i + 12]
        if len(entry) < 12:
            break  # Fin du répertoire ou enregistrement tronqué
        tag    = entry[:3]           # Tag du champ (3 chiffres)
        length = int(entry[3:7])     # Longueur du champ (inclut le \x1e final)
        start  = int(entry[7:12])    # Position de début dans la zone de données
        # On extrait le contenu du champ en soustrayant 1 pour exclure le \x1e final
        data = raw[base + start: base + start + length - 1]
        # Un même tag peut apparaître plusieurs fois (ex. plusieurs formes rejetées 400)
        fields.setdefault(tag, []).append(data)

    return fields


def parse_subfields(field_data: str) -> dict[str, list[str]]:
    """
    Extrait les sous-champs d'un champ UNIMARC variable.

    Structure d'un champ UNIMARC variable :
      [ind1][ind2][\\x1f][code_sf][valeur][\\x1f][code_sf][valeur]...
    Les deux premiers caractères sont les indicateurs (ind1, ind2),
    ignorés ici car non nécessaires pour notre extraction de noms/titres.

    Exemple brut :  "  \\x1faMüller\\x1fbHans\\x1ff1920-2005"
    → {"a": ["Müller"], "b": ["Hans"], "f": ["1920-2005"]}

    On retourne des listes de valeurs car un même code de sous-champ
    peut théoriquement apparaître plusieurs fois dans un champ.
    """
    result: dict[str, list[str]] = {}
    # On saute les 2 premiers caractères (indicateurs), puis on découpe
    # au niveau de chaque séparateur de sous-champ \x1f
    for part in field_data[2:].split(SUBFIELD_DELIM):
        if len(part) >= 2:
            # Le premier caractère est le code du sous-champ, le reste est la valeur
            result.setdefault(part[0], []).append(part[1:])
    return result


def extract_person_name(field_data: str) -> str:
    """
    Reconstruit le nom complet d'une personne depuis un champ 200 ou 400 UNIMARC.

    En UNIMARC autorité personne :
      $a = nom de famille (élément d'entrée)
      $b = prénom(s)
      $f = dates (naissance-décès, ex. "1920-2005")

    On concatène les trois en ignorant les sous-champs absents.
    Exemple : $a="Bourdieu" $b="Pierre" $f="1930-2002" → "Bourdieu Pierre 1930-2002"
    """
    sf = parse_subfields(field_data)
    parts = [
        sf.get("a", [""])[0].strip(),
        sf.get("b", [""])[0].strip(),
        sf.get("f", [""])[0].strip(),
    ]
    # filter(None, ...) supprime les chaînes vides avant le join
    return " ".join(filter(None, parts))


def extract_works(fields_810: list[str]) -> list[str]:
    """
    Extrait les titres d'œuvres depuis les champs 810 (sources bibliographiques).

    Le champ 810 en UNIMARC autorités BnF contient les références
    bibliographiques ayant servi à établir la notice. Le sous-champ $a
    a le format : "Titre de l'œuvre / Auteur / Éditeur, Année"

    On conserve uniquement la partie avant le premier " / " pour isoler
    le titre, qui sera ensuite comparé aux titres de notre base locale.
    Ces titres permettent de valider l'appariement au-delà du seul nom :
    deux homonymes peuvent avoir le même nom mais pas les mêmes œuvres.
    """
    works = []
    for field_data in fields_810:
        for value in parse_subfields(field_data).get("a", []):
            title = value.split(" / ")[0].strip()
            if len(title) > 4:  # On ignore les titres trop courts (bruit)
                works.append(title)
    # dict.fromkeys préserve l'ordre tout en dédoublonnant
    return list(dict.fromkeys(works))


# ── Accès à la base de données ────────────────────────────────────────

def load_authors(conn) -> list[dict]:
    """
    Charge tous les auteurs de la base avec leurs titres associés.

    La jointure avec les tables ecriture et reference permet de récupérer
    pour chaque auteur l'ensemble des titres (title) et titres secondaires
    (secondary_title) des publications qu'il a rédigées. Ces titres serviront
    à valider les appariements avec les œuvres citées dans les notices BnF.

    Structure retournée :
      [{"id": 42, "name": "Bourdieu Pierre", "titles": ["La distinction", ...]}, ...]
    """
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT a.id, a.NomComplet, r.title, r.secondary_title
        FROM authors a
        JOIN ecriture  e ON e.author_id  = a.id
        JOIN reference r ON r.id         = e.reference_id
        WHERE a.NomComplet IS NOT NULL
        ORDER BY a.id
    """)

    # On regroupe les lignes par auteur (un auteur peut avoir N publications,
    # donc la requête retourne N lignes pour cet auteur)
    authors: dict[int, dict] = {}
    for row in cursor.fetchall():
        aid = row["id"]
        if aid not in authors:
            authors[aid] = {"id": aid, "name": row["NomComplet"], "titles": []}
        # On ajoute chaque titre non nul à la liste des titres de l'auteur
        for field in ("title", "secondary_title"):
            if row.get(field):
                authors[aid]["titles"].append(row[field])

    cursor.close()

    # Dédoublonnage des titres par auteur (cas d'un même titre en title et secondary_title)
    for a in authors.values():
        a["titles"] = list(dict.fromkeys(a["titles"]))

    return list(authors.values())


def load_processed_ids() -> set[int]:
    """
    Retourne les author_id déjà présents dans le fichier de sortie.

    Cela permet de reprendre le script là où il s'est arrêté sans
    réexaminer les auteurs déjà traités, ce qui est utile quand les
    fichiers BnF sont volumineux et que le traitement prend plusieurs heures.
    Le fichier de sortie est ouvert en mode "a" (append) dans main(),
    donc les lignes existantes ne sont jamais écrasées.
    """
    ids: set[int] = set()
    try:
        with open(OUTPUT_FILE, encoding="utf-8") as f:
            for line in f:
                try:
                    ids.add(json.loads(line)["author_id"])
                except (json.JSONDecodeError, KeyError):
                    pass  # On ignore les lignes malformées
    except FileNotFoundError:
        pass  # Première exécution : le fichier n'existe pas encore
    return ids


# ── Index inversé sur les tokens de noms ──────────────────────────────

def build_token_index(active: dict[int, dict]) -> dict[str, set[int]]:
    """
    Construit un index inversé { token → ensemble d'author_id } à partir
    des noms normalisés des auteurs à traiter.

    Principe de l'index inversé :
    Au lieu de comparer chaque notice BnF à chaque auteur local (O(n×m)
    comparaisons), on cherche d'abord quels auteurs locaux partagent au
    moins MIN_SHARED_TOKENS tokens avec la notice. Seuls ces candidats
    sont ensuite soumis au calcul de score Levenshtein, beaucoup plus coûteux.

    Exemple avec 3 auteurs :
      "Bourdieu Pierre" → tokens {"bourdieu", "pierre"}
      "Durkheim Emile"  → tokens {"durkheim", "emile"}
      "Pierre Dupont"   → tokens {"pierre", "dupont"}

    Index résultant :
      {"bourdieu": {1}, "pierre": {1, 3}, "durkheim": {2}, "emile": {2}, "dupont": {3}}

    Pour une notice BnF avec tokens {"pierre", "bourdieu"} :
      - "pierre"    → candidats {1, 3}   → token_hits: {1: 1, 3: 1}
      - "bourdieu"  → candidats {1}      → token_hits: {1: 2, 3: 1}
    Avec MIN_SHARED_TOKENS = 2, seul l'auteur 1 passe le filtre.
    """
    index: dict[str, set[int]] = defaultdict(set)
    for aid, author in active.items():
        for token in tokenize(author["name"]):
            index[token].add(aid)
    return index


# ── Calcul du score d'appariement ─────────────────────────────────────

def compute_score(
    author: dict,
    bnf_names: list[str],
    bnf_works: list[str],
) -> tuple[float, str, str] | None:
    """
    Calcule le score d'appariement entre un auteur local et une notice BnF.

    Retourne None si l'un des critères de validation n'est pas satisfait,
    ou un triplet (score_combiné, titre_local, titre_bnf) sinon.

    Logique de validation en cascade (du moins au plus coûteux) :
      1. Vérification de la présence d'œuvres exploitables des deux côtés
         → si l'un manque, on ne peut pas valider par les titres
      2. Filtrage des titres trop courts (bruit documentaire)
      3. Score de nom : on calcule la similarité entre le nom local et tous
         les noms de la notice BnF (vedette + formes rejetées). Si le max
         est < MIN_NAME_SCORE, inutile d'aller plus loin.
      4. Score de titre : on cherche la meilleure paire (titre local, titre BnF).
         C'est l'étape la plus coûteuse (O(n×m) comparaisons Levenshtein).
      5. Score combiné : 60 % nom + 40 % titre. La pondération plus forte
         sur le nom reflète que les titres peuvent être partiellement différents
         (traduction, sous-titre absent) alors que le nom doit être fiable.
    """
    # Étape 1 : vérification de la présence d'œuvres
    if not bnf_works or not author["titles"]:
        return None

    # Étape 2 : filtrage des titres trop courts
    local_titles  = [t for t in author["titles"] if len(normalize(t)) >= MIN_TITLE_LENGTH]
    remote_titles = [t for t in bnf_works        if len(normalize(t)) >= MIN_TITLE_LENGTH]
    if not local_titles or not remote_titles:
        return None

    # Étape 3 : score de nom (pré-filtre rapide)
    # On prend le maximum sur tous les noms de la notice (vedette + variantes)
    # car un auteur peut être entré sous plusieurs formes dans la BnF
    name_score = max((similarity(author["name"], n) for n in bnf_names), default=0.0)
    if name_score < MIN_NAME_SCORE:
        return None

    # Étape 4 : meilleure paire de titres (toutes les combinaisons local × BnF)
    # On utilise un générateur pour éviter de construire une liste intermédiaire
    pairs = ((similarity(lt, wt), lt, wt)
             for lt in local_titles for wt in remote_titles)
    title_score, best_local, best_bnf = max(pairs, key=lambda x: x[0])

    if title_score < THRESHOLD_TITLE:
        return None

    # Étape 5 : score combiné
    combined = 0.6 * name_score + 0.4 * title_score
    if combined < THRESHOLD_COMBINED:
        return None

    return combined, best_local, best_bnf



def main():
    conn    = mysql.connector.connect(**MYSQL_CONFIG)
    authors = load_authors(conn)
    conn.close()

    done   = load_processed_ids()
    active = {a["id"]: a for a in authors if a["id"] not in done}
    print(f"[DB] {len(authors)} auteurs — à traiter : {len(active)}\n")
    if not active:
        return

    token_index = build_token_index(active)
    print(f"[Index] {len(token_index)} tokens distincts\n")

    # ── Initialisation du dictionnaire de résultats ─────────────────
    # Pour chaque auteur actif, on prépare une entrée avec :
    #   - "best" : le meilleur score combiné trouvé jusqu'ici (0.0 au départ)
    #   - "match" : les détails du meilleur appariement (None si aucun trouvé)
    # On conserve le meilleur match au fur et à mesure qu'on parcourt les fichiers,
    # car un même auteur peut être mentionné dans plusieurs notices BnF.
    results = {
        aid: {"author_id": aid, "name": a["name"], "best": 0.0, "match": None}
        for aid, a in active.items()
    }

    # ── Parcours en flux des fichiers BnF ───────────────────────────
    for filepath in sorted(Path(BNF_DATA_DIR).glob("*")):
        for raw in iter_records(str(filepath)):
            fields = parse_record(raw)

            # On ne traite que les notices de personnes physiques.
            # En UNIMARC autorités, le champ 200 est la vedette-matière
            # de la notice de personne ; il est absent des notices de
            # collectivités (210), de titres (230), etc.
            if "200" not in fields:
                continue

            # Identifiant unique BnF de la notice (champ de contrôle 001)
            bnf_id = fields.get("001", [""])[0].strip()

            # Reconstruction de tous les noms de la notice :
            # - champ 200 : vedette principale (nom retenu comme forme officielle)
            # - champ 400 : formes rejetées (variantes orthographiques, pseudonymes,
            #               formes inversées, etc.)
            # Combiner les deux maximise les chances d'appariement avec le nom
            # tel qu'il est stocké dans notre base locale.
            bnf_names = [extract_person_name(fd)
                         for fd in fields.get("200", []) + fields.get("400", [])]
            bnf_names = [n for n in bnf_names if n]  # Suppression des chaînes vides

            # Titres des œuvres citées dans la notice (champ 810)
            bnf_works = extract_works(fields.get("810", []))

            # ── Filtrage par tokens (index inversé) ─────────────────
            # On calcule l'union de tous les tokens des noms de la notice BnF,
            # puis on interroge l'index pour trouver les auteurs locaux
            # qui partagent au moins MIN_SHARED_TOKENS tokens avec elle.
            bnf_tokens = set().union(*(tokenize(n) for n in bnf_names))
            token_hits: dict[int, int] = defaultdict(int)
            for token in bnf_tokens:
                for aid in token_index.get(token, set()):
                    token_hits[aid] += 1  # On compte le nombre de tokens partagés

            # Seuls les auteurs ayant suffisamment de tokens en commun sont retenus
            candidates = [aid for aid, count in token_hits.items()
                          if count >= MIN_SHARED_TOKENS]

            # ── Calcul du score pour chaque candidat ─────────────────
            for aid in candidates:
                result = compute_score(active[aid], bnf_names, bnf_works)
                if result is None:
                    continue
                sc, best_local, best_bnf = result
                # On ne met à jour que si ce score est meilleur que le précédent
                # (un même auteur peut correspondre à plusieurs notices BnF :
                #  on conserve le meilleur appariement)
                if sc > results[aid]["best"]:
                    results[aid]["best"] = sc
                    results[aid]["match"] = {
                        "bnf_id":      bnf_id,
                        "bnf_name":    bnf_names[0],   # Forme principale retenue
                        "score":       round(sc, 4),
                        "title_local": best_local,     # Titre de la base locale ayant fondé le match
                        "title_bnf":   best_bnf,       # Titre BnF correspondant
                    }

    # Une ligne par auteur, qu'il ait été matché ou non (match = null si aucun).
    # Le mode "a" (append) préserve les lignes des exécutions précédentes.
    found = sum(1 for r in results.values() if r["match"])
    print(f"\n{found}/{len(results)} appariements validés — écriture…")

    with open(OUTPUT_FILE, "a", encoding="utf-8") as out:
        for res in results.values():
            out.write(json.dumps(
                {"author_id": res["author_id"], "name": res["name"], "match": res["match"]},
                ensure_ascii=False,   # On conserve les caractères non-ASCII (accents, etc.)
            ) + "\n")

    total = len(results)
    print(f"=== {found}/{total} ({found / total * 100:.1f} %) → {OUTPUT_FILE} ===")


if __name__ == "__main__":
    main()