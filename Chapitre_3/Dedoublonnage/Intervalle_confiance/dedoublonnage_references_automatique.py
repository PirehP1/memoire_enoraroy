"""
Ce programme a pour but de faire un dédoublonnage "agressif" sur la base de données non nettoyée, càd comme elle a été créée avec les RIS de Worldcat. Il créé une nouvelle base de données, "biblio_sans_doublon", afin de permettre le calcul d'un intervalle de confiance entre cette base et celle d'origine, pour voir si nos stratégies de déoublonnage sont dans cet intervalle.
"""
import mysql.connector
import re
import unicodedata
from typing import Optional, List, Dict, Any
from collections import defaultdict
import Levenshtein

DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'PASSWORD',
    'database': 'DATABASE'
}
DB_MANUAL = "references_biblio"
DB_RAW = "bibliographie"
DB_DEST = "biblio_sans_doublon"

def clean_text(text: Optional[str]) -> str:
    """Nettoyage strict : retire HTML, normalise accents et ponctuation."""
    if not text or text == 'NA':
        return ""
    patterns_to_remove = [
        r'</?em>', r'</?i>', r'</?I>', r'</?b>', r'<br\s*/?>', r'</?sup>',
        r'<spanstyle\s*=\s*[^>]*>', r'</span>', r'<xhtml:span[^>]*>', r'</xhtml:span>',
        r'&lt;/?em&gt;', r'&lt;/?i&gt;', r'&lt;/?I&gt;', r'&lt;/?b&gt;',
        r'&lt;br\s*/?&gt;', r'&lt;/?sup&gt;', r';/em&gt;', r'#x[0-9a-fA-F]{4};',
        r'&#[0-9]+;', r'&[a-zA-Z]+;'
    ]
    for pattern in patterns_to_remove:
        text = re.sub(pattern, ' ', text, flags=re.IGNORECASE)
    text = unicodedata.normalize('NFD', text).encode('ascii', 'ignore').decode('utf-8')
    text = re.sub(r'[^\w\s]', ' ', text)
    text = text.lower().strip()
    return re.sub(r'\s+', ' ', text)

def are_matching(str1: str, str2: str, threshold=90) -> bool:
    """Levenshtein.ratio retourne [0,1] ; on ramène au même seuil entier que fuzz."""
    if not str1 or not str2:
        return False
    return Levenshtein.ratio(str1, str2) * 100 >= threshold

# --- LOGIQUE PRINCIPALE ---
def migrate_and_deduplicate():
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)

    cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_DEST} CHARACTER SET utf8mb4")
    cursor.execute(f"DROP TABLE IF EXISTS {DB_DEST}.reference")
    cursor.execute(f"CREATE TABLE {DB_DEST}.reference LIKE {DB_RAW}.reference")
    print(f"Base de destination '{DB_DEST}' initialisée.")

    print(f"Extraction des données (Jointure {DB_RAW} + {DB_MANUAL})...")
    query = f"""
        SELECT r.*,
               COALESCE(m.secondary_title, r.secondary_title) as corrected_sec_title
        FROM {DB_RAW}.reference r
        LEFT JOIN {DB_MANUAL}.reference m ON r.id = m.id
    """
    cursor.execute(query)
    rows = cursor.fetchall()
    total_rows = len(rows)

    print("Normalisation et préparation des comparaisons...")
    for row in rows:
        row['c_title'] = clean_text(row['title'])
        row['c_sec_title'] = clean_text(row['corrected_sec_title'])
        row['c_year'] = str(row['year']).strip() if row['year'] and row['year'] != 'NA' else ""

    rows.sort(key=lambda x: len(x['c_title']))

    # --- Index par année pour le blocking : évite O(n²) ---
    # Chaque nouvelle référence avec une année Y n'est comparée qu'aux
    # uniques ayant la même année ou pas d'année — logique identique à
    # l'ancien filtre "if c_year != u.c_year: continue".
    unique_refs = []
    year_index: Dict[str, List[Dict]] = defaultdict(list)  # année → liste de refs uniques
    no_year_refs: List[Dict] = []                          # refs uniques sans année

    print(f"Analyse de {total_rows} références (Seuil : 90)...")

    for i, row in enumerate(rows):
        if i % (max(1, total_rows // 10)) == 0:
            print(f" Progression : {round((i / total_rows) * 100)}%...")

        if row['c_year']:
            candidates = year_index[row['c_year']] + no_year_refs
        else:
            candidates = unique_refs  # pas d'année = on compare à tout

        is_duplicate = False
        for u in candidates:
            # B. Titre secondaire
            if row['c_sec_title'] and u['c_sec_title']:
                if not are_matching(u['c_sec_title'], row['c_sec_title'], threshold=90):
                    continue
            # C. Titre principal
            if are_matching(u['c_title'], row['c_title'], threshold=90):
                is_duplicate = True
                break

        if not is_duplicate:
            unique_refs.append(row)
            if row['c_year']:
                year_index[row['c_year']].append(row)
            else:
                no_year_refs.append(row)

    print(f"-> {len(unique_refs)} références uniques filtrées sur {total_rows}.")

    if unique_refs:
        print(f"Insertion des données propres dans {DB_DEST}...")
        target_columns = [col for col in rows[0].keys() if not col.startswith('c_') and col != 'corrected_sec_title']
        placeholders = ", ".join(["%s"] * len(target_columns))
        insert_query = f"INSERT INTO {DB_DEST}.reference ({', '.join(target_columns)}) VALUES ({placeholders})"

        data_to_insert = []
        for u in unique_refs:
            u['secondary_title'] = u['corrected_sec_title']
            data_to_insert.append(tuple(u[col] for col in target_columns))

        for i in range(0, len(data_to_insert), 500):
            cursor.executemany(insert_query, data_to_insert[i:i + 500])
            conn.commit()

    cursor.close()
    conn.close()
    print(f"Base de destination : {DB_DEST}")
    print(f"Bases originales {DB_RAW} et {DB_MANUAL} non modifiées.")

if __name__ == "__main__":
    migrate_and_deduplicate()
