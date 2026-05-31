"""
Pour chaque auteur disposant d'au moins un identifiant connu (ORCID, VIAF,
ISNI, IdRef, BNF, GND, Scopus, IEEE, Google Scholar), le script interroge
Wikidata afin de recuperer les identifiants manquants, le genre (P21),
la nationalite (P27) et les langues d'expression (P1412).

Une seule requete SPARQL par auteur (UNION de tous ses identifiants disponibles)
recupere simultanement le QID, les identifiants externes, et les labels
genre/nationalite/langues via SERVICE wikibase:label.
"""

import json
import time
import signal
import requests
import mysql.connector
from pathlib import Path

DB_CONFIG = {
    "host":     "localhost",
    "user":     "root",
    "password": "PASSWORD",
    "database": "DATABASE",
}

OUTPUT_FILE     = Path("wikidata_authors.jsonl")
CHECKPOINT_FILE = Path("wikidata_checkpoint.json")

REQUEST_DELAY   = 2.0 #délai entre chaque requête
BACKOFF_INITIAL = 60
BACKOFF_MAX     = 600
BACKOFF_FACTOR  = 2
MAX_RETRIES     = 4

HEADERS = {
    "User-Agent": "wikidata-author-enrichment/3.0 adresse.mail.placeholder@nomdedomaine.fr",
    "Accept":     "application/json",
}

# (colonne MySQL, propriete Wikidata, label court)
IDENTIFIER_MAP = [
    ("orcid",            "P496",  "orcid"),
    ("PPN_VIAF",         "P214",  "viaf"),
    ("isni",             "P213",  "isni"),
    ("PPN_IDREF",        "P269",  "idref"),
    ("bnf",              "P268",  "bnf"),
    ("GND",              "P227",  "gnd"),
    ("scopusid",         "P1153", "scopus"),
    ("ieee",             "P6479", "ieee"),
    ("googlescholarid",  "P1960", "googlescholar"),
]

# QIDs de genre frequents pre-cached pour eviter des appels EntityData en fallback
LABEL_CACHE = {
    "Q6581097": "masculin",             "Q6581072": "feminin",
    "Q1052281": "feminin (transgenre)", "Q2449503": "masculin (transgenre)",
    "Q48270":   "non-binaire",          "Q1097630": "intersexe",
}

_shutdown_requested = False

# ---------------------------------------------------------------------------
# Arret propre
# ---------------------------------------------------------------------------

def _signal_handler(sig, frame):
    global _shutdown_requested
    print("\n\n[!] Ctrl+C recu — arret apres l'auteur courant...")
    _shutdown_requested = True

signal.signal(signal.SIGINT, _signal_handler)

# ---------------------------------------------------------------------------
# Base de donnees
# ---------------------------------------------------------------------------

def fetch_authors():
    """Retourne tous les auteurs ayant au moins un identifiant connu."""
    cols      = [col for col, _, _ in IDENTIFIER_MAP]
    condition = " OR ".join(f'({c} IS NOT NULL AND TRIM({c}) != "")' for c in cols)
    select    = ", ".join(["id", "NomComplet"] + cols)
    conn   = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT {select} FROM authors WHERE {condition}")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows

# ---------------------------------------------------------------------------
# Checkpoint
# ---------------------------------------------------------------------------

def load_checkpoint():
    """Retourne le dernier id traite, ou 0 si aucun checkpoint."""
    try:
        data = json.loads(CHECKPOINT_FILE.read_text(encoding="utf-8"))
        last_id = int(data["last_id"])
        print(f"[checkpoint] reprise depuis id > {last_id}")
        return last_id
    except Exception:
        return 0

def save_checkpoint(last_id):
    CHECKPOINT_FILE.write_text(json.dumps({"last_id": last_id}), encoding="utf-8")

# ---------------------------------------------------------------------------
# Normalisation des identifiants
# ---------------------------------------------------------------------------

def clean_identifier(prop, value):
    """Normalise la valeur brute d'un identifiant selon les conventions Wikidata."""
    value = str(value).strip()
    if prop == "P214":
        value = value.replace("http://viaf.org/viaf/", "").strip("/")
    elif prop == "P213":
        v = value.replace(" ", "")
        if len(v) == 16:
            value = f"{v[0:4]} {v[4:8]} {v[8:12]} {v[12:16]}"
    elif prop == "P268":
        if "/" in value:
            value = value.rsplit("/", 1)[-1]
        if value.lower().startswith("cb"):
            value = value[2:]
    return value

# ---------------------------------------------------------------------------
# Couche reseau
# ---------------------------------------------------------------------------

def _get(url, params=None, tag="requete"):
    """GET avec retry et backoff exponentiel. Retourne le JSON ou None."""
    backoff = BACKOFF_INITIAL
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
            if resp.status_code == 429:
                wait = max(int(resp.headers.get("Retry-After", backoff)), backoff)
                print(f"    [429] {tag} — attente {wait}s (tentative {attempt}/{MAX_RETRIES})")
                time.sleep(wait)
                backoff = min(backoff * BACKOFF_FACTOR, BACKOFF_MAX)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as exc:
            print(f"    [erreur HTTP] {tag} : {exc} (tentative {attempt}/{MAX_RETRIES})")
            if attempt < MAX_RETRIES:
                time.sleep(backoff)
                backoff = min(backoff * BACKOFF_FACTOR, BACKOFF_MAX)
        except requests.exceptions.RequestException as exc:
            print(f"    [erreur reseau] {tag} : {exc} (tentative {attempt}/{MAX_RETRIES})")
            if attempt < MAX_RETRIES:
                time.sleep(min(backoff, 30))
    print(f"    [abandon] {tag} apres {MAX_RETRIES} tentatives")
    return None

def get_label(qid):
    """
    Retourne le label fr/en d'un QID via EntityData (fallback uniquement).
    Resultat mis en cache. Delai de courtoisie de 0,5s apres chaque requete.
    """
    if qid in LABEL_CACHE:
        return LABEL_CACHE[qid]
    data   = _get(f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json",
                  tag=f"EntityData {qid}")
    labels = (data or {}).get("entities", {}).get(qid, {}).get("labels", {})
    label  = (labels.get("fr") or labels.get("en") or {}).get("value", qid)
    time.sleep(0.5)
    LABEL_CACHE[qid] = label
    return label


def sparql_find_entity(author_row):
    """
    Requete SPARQL unique (UNION de tous les identifiants disponibles) qui
    recupere simultanement : QID, identifiants externes (OPTIONAL), genre,
    nationalite, langues, et leurs labels via SERVICE wikibase:label.

    Retourne (source_prop, source_value, bindings) ou (None, None, []).
    source_prop/source_value : premier identifiant matche, pour identifiant_source.
    """
    union_clauses = []
    available = []
    for col, prop, label in IDENTIFIER_MAP:
        raw = author_row.get(col)
        if not raw:
            continue
        value = clean_identifier(prop, raw)
        available.append((prop, value, label))
        union_clauses.append(
            f'{{ ?item wdt:{prop} "{value}" . BIND("{prop}" AS ?src_prop) BIND("{value}" AS ?src_val) }}'
        )

    if not union_clauses:
        return None, None, []

    optionals_ids = "\n      ".join(
        f"OPTIONAL {{ ?item wdt:{prop} ?{label}_ . }}"
        for _col, prop, label in IDENTIFIER_MAP
    )
    id_vars = " ".join(f"?{label}_" for _col, _prop, label in IDENTIFIER_MAP)

    query = f"""
SELECT DISTINCT ?item ?src_prop ?src_val
       ?genreQid ?genreLabel
       ?nationaliteQid ?nationaliteLabel
       ?langueQid ?langueLabel
       {id_vars}
WHERE {{
  {" UNION ".join(union_clauses)}
  OPTIONAL {{ ?item wdt:P21   ?genreQid . }}
  OPTIONAL {{ ?item wdt:P27   ?nationaliteQid . }}
  OPTIONAL {{ ?item wdt:P1412 ?langueQid . }}
  {optionals_ids}
  SERVICE wikibase:label {{
    bd:serviceParam wikibase:language "fr,en" .
    ?genreQid       rdfs:label ?genreLabel .
    ?nationaliteQid rdfs:label ?nationaliteLabel .
    ?langueQid      rdfs:label ?langueLabel .
  }}
}}
"""
    print(f"    -> SPARQL UNION ({len(union_clauses)} identifiant(s))")
    data = _get("https://query.wikidata.org/sparql",
                params={"query": query, "format": "json"},
                tag="SPARQL UNION")
    if not data:
        return None, None, []

    bindings = data.get("results", {}).get("bindings", [])
    if not bindings:
        return None, None, []

    matched_props = {b["src_prop"]["value"] for b in bindings}
    matched       = [(p, v, l) for p, v, l in available if p in matched_props]
    source_prop, source_value, _ = matched[0]

    qid         = bindings[0]["item"]["value"].split("/")[-1]
    matched_str = ", ".join(f"{l}={v!r}" for _, v, l in matched)
    print(f"    -> QID trouve : {qid} (identifiants matches : {matched_str})")
    return source_prop, source_value, bindings


def parse_sparql_bindings(bindings, source_prop, source_value):
    """
    Construit le dict de resultats depuis les bindings SPARQL.
    Fallback sur get_label() si un label est absent des bindings.
    """
    if not bindings:
        return None

    first  = bindings[0]
    qid    = first["item"]["value"].split("/")[-1]
    result = {"wikidata_qid": qid, "identifiants": {}}

    for _col, prop, label in IDENTIFIER_MAP:
        var = f"{label}_"
        if var in first and first[var].get("value"):
            result["identifiants"][label] = {"valeur": first[var]["value"],
                                             "propriete_wikidata": prop}

    for key, qid_var, label_var, pwdt in [
        ("genre",      "genreQid",      "genreLabel",      "P21"),
        ("nationalite","nationaliteQid","nationaliteLabel", "P27"),
    ]:
        if first.get(qid_var, {}).get("value"):
            q = first[qid_var]["value"].split("/")[-1]
            result[key] = {
                "label":              first.get(label_var, {}).get("value") or get_label(q),
                "wikidata_qid":       q,
                "propriete_wikidata": pwdt,
            }

    seen, langues = set(), []
    for b in bindings:
        if not b.get("langueQid", {}).get("value"):
            continue
        q = b["langueQid"]["value"].split("/")[-1]
        if q in seen:
            continue
        seen.add(q)
        langues.append({"label":        b.get("langueLabel", {}).get("value") or get_label(q),
                        "wikidata_qid": q})
    if langues:
        result["langues_expression"] = {"valeurs": langues, "propriete_wikidata": "P1412"}

    result["identifiant_source"] = {"propriete_wikidata": source_prop, "valeur": source_value}
    return result


def enrich_author(author_row):
    """Requete SPARQL unique, retourne le dict enrichi ou None."""
    source_prop, source_value, bindings = sparql_find_entity(author_row)
    time.sleep(REQUEST_DELAY)
    return parse_sparql_bindings(bindings, source_prop, source_value) if bindings else None

def main():
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    last_id = load_checkpoint()
    authors = [a for a in fetch_authors() if a["id"] > last_id]
    total   = len(authors)
    print(f"{total} auteurs restants a traiter (checkpoint id > {last_id})")

    found = not_found = 0

    with OUTPUT_FILE.open("a", encoding="utf-8") as fout:
        for i, author in enumerate(authors, 1):
            if _shutdown_requested:
                print("[!] Arret propre — progression sauvegardee.")
                break

            author_id = author["id"]
            nom       = author.get("NomComplet") or ""
            print(f"[{i}/{total}] id={author_id} | {nom}")

            enriched = enrich_author(author)

            fout.write(json.dumps(
                {"id_bdd": author_id, "nom_complet": nom, "wikidata": enriched},
                ensure_ascii=False) + "\n")
            fout.flush()
            save_checkpoint(author_id)

            if enriched:
                found += 1
            else:
                not_found += 1
                print("    aucun resultat Wikidata")

    print(f"\nSession terminee : {found} enrichis, {not_found} sans resultat.")
    print(f"Sortie : {OUTPUT_FILE.resolve()}")
    if not _shutdown_requested:
        CHECKPOINT_FILE.unlink(missing_ok=True)
        print("Checkpoint supprime (traitement complet).")


if __name__ == "__main__":
    main()
