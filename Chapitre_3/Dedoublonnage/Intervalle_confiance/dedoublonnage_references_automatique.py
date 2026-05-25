"""
Ce programme a pour but de faire un dédoublonnage "agressif" sur la base de données non nettoyée, càd comme elle a été créée avec les RIS de Worldcat. Il créé une nouvelle base de données, "biblio_sans_doublon", afin de permettre le calcul d'un intervalle de confiance entre cette base et celle d'origine, pour voir si nos stratégies de déoublonnage sont dans cet intervalle.
"""

import mysql.connector
import re
import unicodedata
from typing import Optional, List, Dict, Any
from thefuzz import fuzz 

# --- CONFIGURATION DES BASES ---
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'PASSWORD',
    'database': 'bibliographie' # Base de connexion par défaut
}

DB_MANUAL = "references_biblio"  # Base contenant vos corrections (non modifiée)
DB_RAW = "bibliographie"        # Base contenant les doublons (non modifiée)
DB_DEST = "biblio_sans_doublon"  # Base destination (créée par le script)


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
    
    # Suppression des accents
    text = unicodedata.normalize('NFD', text).encode('ascii', 'ignore').decode('utf-8')
    # Remplacement de toute ponctuation par un espace
    text = re.sub(r'[^\w\s]', ' ', text)
    text = text.lower().strip()
    return re.sub(r'\s+', ' ', text)

def are_matching(str1: str, str2: str, threshold=90) -> bool:
    """Utilise partial_ratio pour permettre des variations mineures ou des titres longs."""
    if not str1 or not str2: return False
    return fuzz.partial_ratio(str1, str2) >= threshold

# --- LOGIQUE PRINCIPALE ---

def migrate_and_deduplicate():
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)
    
    # 1. Préparation de la base de destination (elle seule est modifiée/écrasée)
    cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_DEST} CHARACTER SET utf8mb4")
    cursor.execute(f"DROP TABLE IF EXISTS {DB_DEST}.reference")
    cursor.execute(f"CREATE TABLE {DB_DEST}.reference LIKE {DB_RAW}.reference")
    print(f"Base de destination '{DB_DEST}' initialisée.")

    # 2. Récupération des données avec Jointure pour les titres secondaires corrigés
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

    # 3. Pré-nettoyage et tri par longueur
    print("Normalisation et préparation des comparaisons...")
    for row in rows:
        row['c_title'] = clean_text(row['title'])
        row['c_sec_title'] = clean_text(row['corrected_sec_title'])
        row['c_year'] = str(row['year']).strip() if row['year'] and row['year'] != 'NA' else ""

    # Tri : le plus court d'abord (servira de base de comparaison)
    rows.sort(key=lambda x: len(x['c_title']))

    # 4. Algorithme de déduplication
    unique_refs = []
    print(f"Analyse de {total_rows} références (Seuil : 90)...")
    
    for i, row in enumerate(rows):
        if i % (max(1, total_rows // 10)) == 0:
            print(f" Progression : {round((i/total_rows)*100)}%...")

        is_duplicate = False
        for u in unique_refs: 
            # A. Année : Si les deux ont une année, elle doit être identique
            if row['c_year'] and u['c_year'] and row['c_year'] != u['c_year']:
                continue
            
            # B. Titre Secondaire : Tolérant (pour gérer les "Édité par..." ou sigles)
            # On passe de l'égalité stricte à un partial_ratio à 90
            if row['c_sec_title'] and u['c_sec_title']:
                if not are_matching(u['c_sec_title'], row['c_sec_title'], threshold=90):
                    continue

            # C. Titre Principal : Seuil abaissé à 90 pour gérer "exact" vs "exakt"
            if are_matching(u['c_title'], row['c_title'], threshold=90):
                is_duplicate = True
                break
        
        if not is_duplicate:
            unique_refs.append(row)

    print(f"-> {len(unique_refs)} références uniques filtrées sur {total_rows}.")
    
    # 5. Migration des données
    if unique_refs:
        print(f"Insertion des données propres dans {DB_DEST}...")
        
        # Identification des colonnes valides pour la table cible
        target_columns = [col for col in rows[0].keys() if not col.startswith('c_') and col != 'corrected_sec_title']
        placeholders = ", ".join(["%s"] * len(target_columns))
        insert_query = f"INSERT INTO {DB_DEST}.reference ({', '.join(target_columns)}) VALUES ({placeholders})"
        
        data_to_insert = []
        for u in unique_refs:
            # On injecte le titre secondaire corrigé (uniformisé) dans la base finale
            u['secondary_title'] = u['corrected_sec_title']
            data_to_insert.append(tuple(u[col] for col in target_columns))
        
        # Insertion par lots
        for i in range(0, len(data_to_insert), 500):
            cursor.executemany(insert_query, data_to_insert[i:i+500])
            conn.commit()

    cursor.close()
    conn.close()
    print(f"Base de destination : {DB_DEST}")
    print(f"Bases originales {DB_RAW} et {DB_MANUAL} non modifiées.")

if __name__ == "__main__":
    migrate_and_deduplicate()