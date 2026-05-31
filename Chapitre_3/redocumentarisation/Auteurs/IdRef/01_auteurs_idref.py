"""
──────────────
1. Charge les auteurs sans ppn_idref depuis MySQL (avec leurs titres locaux)
2. Interroge l'API IdRef : Solr (candidats) puis /services/biblio/{PPN}.json (œuvres)
3. Compare via distance de Levenshtein — s'arrête dès qu'un PPN est validé
4. Écrit les résultats dans idref_candidates.jsonl (reprise possible)
"""

import json
import re
import time
import unicodedata
import requests
import mysql.connector
import Levenshtein
from typing import Optional

MYSQL_CONFIG = {
    "host":     "localhost",
    "user":     "root",
    "password": "PASSWORD",
    "database": "DATABASE",
}

IDREF_SOLR_URL   = "https://www.idref.fr/Sru/Solr"
IDREF_BIBLIO_URL = "https://www.idref.fr/services/biblio/{ppn}.json"

OUTPUT_FILE    = "idref_candidates.jsonl"
MAX_CANDIDATES = 10      # Nombre max de PPN testés par auteur
THRESHOLD      = 0.8    # Score Levenshtein minimum pour valider
REQUEST_DELAY  = 1    # Pause (s) entre appels API

# ──────────────────────────────────────────────
# UTILITAIRES TEXTE
# ──────────────────────────────────────────────

def normalize(text: str) -> str:
    """Minuscules, suppression des accents, ponctuation et espaces multiples."""
    if not isinstance(text, str):
        return ""
    text = text.lower()
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("utf-8")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def lev_ratio(a: str, b: str) -> float:
    """Ratio de similarité Levenshtein normalisé (0.0 → 1.0)."""
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return 0.0
    # Containment fort → score maximal direct
    if len(na) > 10 and len(nb) > 10 and (na in nb or nb in na):
        return 1.0
    return Levenshtein.ratio(na, nb)


def best_score(local_titles: list[str], idref_works: list[str]) -> tuple[float, str, str]:
    """
    Compare toutes les paires (titre local × titre IdRef).
    Retourne (meilleur_score, titre_local, titre_idref).
    """
    best, bl, bi = 0.0, "", ""
    for lt in local_titles:
        for it in idref_works:
            s = lev_ratio(lt, it)
            if s > best:
                best, bl, bi = s, lt, it
                if best >= 1.0:
                    return best, bl, bi
    return best, bl, bi

# ──────────────────────────────────────────────
# BASE DE DONNÉES
# ──────────────────────────────────────────────

def load_authors(conn) -> list[dict]:
    """
    Charge les auteurs sans ppn_idref avec leurs titres locaux.
    Une seule requête JOIN au lieu d'une requête par auteur.
    """
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT a.id, a.NomComplet, r.title, r.secondary_title
        FROM authors a
        JOIN ecriture e  ON e.author_id   = a.id
        JOIN reference r ON r.id          = e.reference_id
        WHERE (a.ppn_idref IS NULL OR a.ppn_idref = '')
          AND a.NomComplet IS NOT NULL
          AND a.NomComplet != ''
        ORDER BY a.id
    """)
    rows = cur.fetchall()
    cur.close()
 
    # Regroupement des titres par auteur (ordre d'insertion préservé)
    authors: dict[int, dict] = {}
    for row in rows:
        aid = row["id"]
        if aid not in authors:
            authors[aid] = {"id": aid, "NomComplet": row["NomComplet"], "local_titles": []}
        for field in ("title", "secondary_title"):
            if row.get(field):
                authors[aid]["local_titles"].append(row[field])
 
    # Dédoublonnage des titres + filtre auteurs sans titre
    results = []
    for a in authors.values():
        a["local_titles"] = list(dict.fromkeys(a["local_titles"]))
        if a["local_titles"]:
            results.append(a)
 
    print(f"[DB] {len(results)} auteurs à traiter (avec titres locaux)\n")
    return results



def already_processed() -> set[int]:
    """IDs déjà présents dans le fichier de sortie (pour reprise)."""
    ids: set[int] = set()
    try:
        with open(OUTPUT_FILE, encoding="utf-8") as f:
            for line in f:
                try:
                    ids.add(json.loads(line)["author_id"])
                except Exception:
                    pass
    except FileNotFoundError:
        pass
    return ids

# ──────────────────────────────────────────────
# API IDREF
# ──────────────────────────────────────────────

def search_solr(name: str) -> list[dict]:
    """Retourne jusqu'à MAX_CANDIDATES PPN candidats triés par pertinence."""
    tokens = [t for t in re.sub(r"['.,-/]", " ", name).split() if len(t) > 1]
    if not tokens:
        return []
    query = "persname_t:(" + " AND ".join(tokens) + ") AND recordtype_z:a"
    try:
        resp = requests.get(
            IDREF_SOLR_URL,
            params={
                "q": query,
                "wt": "json",
                "rows": MAX_CANDIDATES,
                "fl": "ppn_z,affcourt_z,recordtype_z",
                "sort": "score desc",
            },
            timeout=10,
        )
        resp.raise_for_status()
        docs = resp.json().get("response", {}).get("docs", [])
        return [{"ppn": d["ppn_z"], "label": d.get("affcourt_z", name)} for d in docs if "ppn_z" in d]
    except Exception as e:
        print(f"  [Solr] Erreur : {e}")
        return []


def fetch_biblio(ppn: str) -> Optional[dict]:
    """
    Appelle /services/biblio/{PPN}.json et retourne le JSON parsé.
    """
    url = IDREF_BIBLIO_URL.format(ppn=ppn)
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"  [Biblio] PPN {ppn} : {e}")
        return None


def extract_works(biblio_json: dict) -> list[str]:
    """
    Extrait les titres depuis le JSON /services/biblio/{PPN}.json.

    Chaque rôle (auteur, éditeur, directeur…) contient une liste de docs.
    Chaque doc a un champ 'citation' de la forme :
        "Titre  / Auteur / Éditeur , Année"
    On prend la partie avant le premier ' / ' comme titre.
    """
    works: list[str] = []
    try:
        roles = biblio_json.get("sudoc", {}).get("result", {}).get("role", [])
        if isinstance(roles, dict):
            roles = [roles]   # Un seul rôle → le mettre dans une liste

        for role in roles:
            docs = role.get("doc", [])
            if isinstance(docs, dict):
                docs = [docs]   # Un seul doc → idem

            for doc in docs:
                citation = doc.get("citation", "").strip()
                if not citation:
                    continue
                # Le titre est la partie avant le premier séparateur "  / "
                title = citation.split(" / ")[0].strip()
                if len(title) > 4:
                    works.append(title)

    except Exception as e:
        print(f"  [extract_works] Erreur : {e}")

    return list(dict.fromkeys(works))   # Dédoublonnage, ordre préservé

# ──────────────────────────────────────────────
# TRAITEMENT PAR AUTEUR
# ──────────────────────────────────────────────

def process_author(author: dict) -> dict:
    name         = author["NomComplet"]
    local_titles = author["local_titles"]

    print(f"[{author['id']}] {name}  ({len(local_titles)} titre(s) local/aux)")

    candidates_raw = search_solr(name)
    print(f"  → {len(candidates_raw)} candidat(s) Solr")

    candidates_tried: list[dict] = []
    match: Optional[dict]        = None

    for i, cand in enumerate(candidates_raw[:MAX_CANDIDATES]):
        ppn, label = cand["ppn"], cand["label"]
        print(f"  [{i+1}] PPN {ppn} – {label}")

        time.sleep(REQUEST_DELAY)
        biblio_raw = fetch_biblio(ppn)
        works      = extract_works(biblio_raw) if biblio_raw else []

        print(f"       {len(works)} œuvre(s)")
        candidates_tried.append({"ppn": ppn, "label": label, "works": works})

        score, ml, mi = best_score(local_titles, works)
        if score >= THRESHOLD:
            match = {"ppn": ppn, "label": label, "score": round(score, 4),
                     "matched_local": ml, "matched_idref": mi, "ppn_rank": i + 1}
            print(f"MATCH score={score:.3f}  « {ml} »")
            break #pour arrêter de query l'API, permet de pas tester 10 ppn

    if not match:
        print("Aucun PPN validé")

    return {
        "author_id":        author["id"],
        "name":             name,
        "local_titles":     local_titles,
        "candidates_tried": candidates_tried,
        "match":            match,
    }

# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────

def main():
    try:
        conn = mysql.connector.connect(**MYSQL_CONFIG)
    except mysql.connector.Error as e:
        print(f"[DB] Connexion impossible : {e}")
        return

    authors   = load_authors(conn)
    conn.close()

    done_ids  = already_processed()
    if done_ids:
        authors = [a for a in authors if a["id"] not in done_ids]
        print(f"Reprise : {len(done_ids)} déjà traités, {len(authors)} restants\n")

    if not authors:
        print("Rien à traiter.")
        return

    found = 0
    with open(OUTPUT_FILE, "a", encoding="utf-8") as out:
        for idx, author in enumerate(authors, 1):
            print(f"\n── {idx}/{len(authors)} ──")
            result = process_author(author)
            out.write(json.dumps(result, ensure_ascii=False) + "\n")
            out.flush()
            if result["match"]:
                found += 1

    total = len(authors)
    print(f"\n=== Fin : {found}/{total} identifiés ({found/total*100:.1f} %) ===")
    print(f"Résultats : {OUTPUT_FILE}")


if __name__ == "__main__":
    main()