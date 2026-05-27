"""
crossref_to_db.py
-----------------
Lit le fichier crossref_full_dump.json produit par crossref_full_dump.py
et enrichit la base de donnees avec les metadonnees recuperees depuis CrossRef.

Trois operations sont effectuees pour chaque reference :
  1. Mise a jour des champs NULL ou vides de la table reference.
  2. Creation dans authors des auteurs absents (identification par NomComplet).
  3. Etablissement des liens dans ecriture (si aucun auteur n'y est deja lie).

Principe de non-ecrasement : un champ deja renseigne dans la base n'est
jamais remplace par la valeur CrossRef.
"""

import json
import mysql.connector
from typing import Optional, Dict, List

DB_CONFIG = {
    'host':     'localhost',
    'user':     'root',
    'password': 'PASSWORD',
    'database': 'DATABASE',
}

INPUT_FILE = 'crossref_full_dump.json'

# Note sur le champ type_of_reference (non traite ici)
# -------------------------------------------------------
# CrossRef expose un champ 'type' dont le vocabulaire controlled est distinct des codes RIS stockes dans la colonne type_of_reference de la base.
# Une correspondance est theoriquement possible (ex. 'journal-article' -> 'JOUR',
# 'book-chapter' -> 'CHAP', 'dissertation' -> 'THES'), mais la taxonomie CrossRef  est plus granulaire et son mapping vers RIS est parfois ambigu (ex. 'posted-content' peut designer une preprint ou une note de blog selon le contexte).
# Par prudence, ce champ n'est pas mis a jour automatiquement : une verification
# manuelle ou une etape de reconciliation dediee serait preferable.
# Surtout, cela résulte d'une appréhension limitée de ce que pouvait renvoyer Crossref : les échantillons examinés n'ont pas permis de rendre compte de la diversité des types renvoyés.

def extract_year(date_field: Optional[Dict]) -> Optional[str]:
    """Extrait l'annee depuis un objet date CrossRef (format date-parts)."""
    if date_field and 'date-parts' in date_field:
        parts = date_field['date-parts']
        if parts and parts[0]:
            return str(parts[0][0])
    return None


def extract_fields(crossref: Dict) -> Dict:
    """
    Transforme le JSON CrossRef en un dictionnaire de champs directement
    inserables dans la table reference.

    Priorites pour l'annee : published-print > issued > published.
    Pour les pages, seule la page de debut est extraite ("421-427" -> "421").
    """
    year = (
        extract_year(crossref.get('published-print')) or
        extract_year(crossref.get('issued'))           or
        extract_year(crossref.get('published'))
    )

    page_raw   = crossref.get('page') or ''
    start_page = page_raw.split('-')[0].strip() if page_raw else None

    issn_list      = crossref.get('ISSN') or []
    container_list = crossref.get('container-title') or []
    links          = crossref.get('link') or []

    return {
        'year':              year,
        'start_page':        start_page,
        'issn':              issn_list[0]      if issn_list      else None,
        'secondary_title':   container_list[0] if container_list else None,
        'language':          crossref.get('language'),
        'abstract':          crossref.get('abstract'),
        'url':               crossref.get('URL'),
        'link':              links[0]['URL']   if links          else None,
        'volume':            crossref.get('volume'),
        'number':            crossref.get('issue'),
        'publisher':         crossref.get('publisher'),
    }


# ---------------------------------------------------------------------------
# Operations sur la base de donnees
# ---------------------------------------------------------------------------

def update_reference(cursor, ref_id: int, fields: Dict) -> bool:
    """
    Met a jour uniquement les colonnes NULL ou vides de la table reference.
    Retourne True si au moins une colonne a ete modifiee.
    """
    set_clauses, values = [], []
    for col, val in fields.items():
        if val is None:
            continue
        # La clause IF garantit qu'un champ deja renseigne n'est pas ecrase.
        set_clauses.append(
            f"`{col}` = IF(`{col}` IS NULL OR `{col}` = '', %s, `{col}`)"
        )
        values.append(val)

    if not set_clauses:
        return False

    values.append(ref_id)
    cursor.execute(
        f"UPDATE `reference` SET {', '.join(set_clauses)} WHERE id = %s",
        values
    )
    return cursor.rowcount > 0


def get_or_create_author(cursor, family: str, given: str) -> int:
    """
    Recherche un auteur par NomComplet ("Famille, Prenom").
    L'insere dans authors s'il est absent, avec methode_recup = 'crossref'.
    Retourne l'identifiant de l'auteur (existant ou nouvellement cree).
    """
    nom_complet = f"{family}, {given}".strip(', ')

    cursor.execute(
        "SELECT id FROM authors WHERE NomComplet = %s",
        (nom_complet,)
    )
    row = cursor.fetchone()
    if row:
        return row['id']

    cursor.execute(
        """
        INSERT INTO authors (NomComplet, Nom, Prenom, methode_recup)
        VALUES (%s, %s, %s, 'crossref')
        """,
        (nom_complet, family or None, given or None)
    )
    return cursor.lastrowid


def process_authors(cursor, ref_id: int, crossref: Dict) -> int:
    """
    Lie les auteurs CrossRef a une reference via la table ecriture.

    Si des auteurs sont deja associes a la reference dans ecriture,
    aucune modification n'est effectuee (principe de non-ecrasement).
    Retourne le nombre d'auteurs nouvellement lies.
    """
    authors = crossref.get('author') or []
    if not authors:
        return 0

    cursor.execute(
        "SELECT COUNT(*) AS cnt FROM ecriture WHERE reference_id = %s",
        (ref_id,)
    )
    if cursor.fetchone()['cnt'] > 0:
        return 0

    count = 0
    for order, author in enumerate(authors, 1):
        family = (author.get('family') or '').strip()
        given  = (author.get('given')  or '').strip()
        if not family and not given:
            continue

        author_id = get_or_create_author(cursor, family, given)
        cursor.execute(
            """
            INSERT IGNORE INTO ecriture (reference_id, author_id, author_order)
            VALUES (%s, %s, %s)
            """,
            (ref_id, author_id, order)
        )
        count += 1

    return count


# ---------------------------------------------------------------------------
# Programme principal
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"Chargement de {INPUT_FILE}...")
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        records = json.load(f)

    exploitables = [r for r in records if r.get('found') and r.get('crossref')]
    print(f"{len(records)} entrees totales, {len(exploitables)} avec donnees CrossRef.\n")

    conn   = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)

    refs_maj    = 0
    auteurs_lie = 0
    erreurs     = 0

    for i, record in enumerate(exploitables, 1):
        ref_id   = record['db_id']
        crossref = record['crossref']

        print(f"[{i}/{len(exploitables)}] ID {ref_id} — DOI : {record['doi']}")

        try:
            fields  = extract_fields(crossref)
            updated = update_reference(cursor, ref_id, fields)
            if updated:
                refs_maj += 1
                print(f"    reference mise a jour.")
            else:
                print(f"    aucun champ vide a renseigner.")

            n = process_authors(cursor, ref_id, crossref)
            if n:
                auteurs_lie += n
                print(f"    {n} auteur(s) associe(s).")

            conn.commit()

        except Exception as exc:
            conn.rollback()
            print(f"    ERREUR : {exc}")
            erreurs += 1

    cursor.close()
    conn.close()

    print(f"\nTermine.")
    print(f"  References mises a jour : {refs_maj}")
    print(f"  Auteurs lies            : {auteurs_lie}")
    print(f"  Erreurs                 : {erreurs}")


if __name__ == "__main__":
    main()