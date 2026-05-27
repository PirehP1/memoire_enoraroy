"""
Script 01 – Détection de langue via l'API CrossRef
Pour les références possédant un DOI, interrogation de l'API CrossRef.
Entrée  : base MySQL
Sortie  : resultats_01.json  {id, langue, source_langue}
"""

import json
import time
import requests
import mysql.connector

# ── Configuration ────────────────────────────────────────────────────────────

DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'PASSWORD',
    'database': 'DATABASE',
    'charset': 'utf8mb4'
}

OUTPUT_JSON_01 = 'resultats_01.json'

HEADERS = {
    'User-Agent': 'BiblioLangDetector/1.0 (Academic Research)'
}

# Codes ISO académiques reconnus
ACADEMIC_LANGUAGES = {
    'en', 'fr', 'de', 'it', 'es', 'pt', 'nl', 'pl', 'ru', 'ar', 'zh', 'ja',
    'tr', 'el', 'cs', 'ro', 'hu', 'sv', 'no', 'da', 'fi', 'uk',
    'ca', 'hr', 'sk', 'bg', 'lt', 'sl', 'et', 'lv',
    'ko', 'vi', 'th', 'id',
}

# ── Normalisation du code de langue ─────────────────────────────────────────

def normalize(code) -> str | None:
    """Ramène un code brut (ex. 'en-US', 'French') à un code ISO court."""
    if not code or not isinstance(code, str):
        return None
    code = code.lower().strip()
    code = code.split('-')[0].split('_')[0]
    aliases = {'english': 'en', 'french': 'fr', 'german': 'de',
               'spanish': 'es', 'italian': 'it', 'arabic': 'ar',
               'chinese': 'zh', 'russian': 'ru', 'turkish': 'tr'}
    code = aliases.get(code, code)
    return code if code in ACADEMIC_LANGUAGES else None

# ── Interrogation CrossRef ────────────────────────────────────────────────────

def query_crossref(doi: str, session: requests.Session) -> str | None:
    """
    Interroge l'API CrossRef pour un DOI donné.
    Retourne le code de langue normalisé, ou None si absent/non reconnu.
    """
    try:
        resp = session.get(
            f"https://api.crossref.org/works/{doi}",
            headers=HEADERS,
            timeout=10
        )
        if resp.status_code == 200:
            message = resp.json().get('message', {})
            return normalize(message.get('language'))
    except requests.RequestException as e:
        print(f"  [erreur CrossRef] {e}")
    return None

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    conn   = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT id, doi
        FROM reference
        WHERE (language IS NULL OR language = '')
          AND doi IS NOT NULL AND doi != ''
        ORDER BY id
    """)
    refs = cursor.fetchall()
    cursor.close()
    conn.close()

    print(f"{len(refs)} références à traiter\n")

    results = []
    session = requests.Session()

    for i, ref in enumerate(refs, 1):
        ref_id = ref['id']
        doi    = ref['doi'].strip()

        print(f"[{i}/{len(refs)}] ID {ref_id} | DOI {doi}")

        lang = query_crossref(doi, session)

        if lang:
            print(f"  -> {lang} (crossref_api)")
            results.append({
                'id':            ref_id,
                'langue':        lang,
                'source_langue': 'crossref_api'
            })
        else:
            print(f"  -> aucune langue CrossRef")

        # Sauvegarde intermédiaire tous les 10
        if i % 10 == 0:
            with open(OUTPUT_JSON_01, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"  [sauvegarde intermédiaire: {len(results)} résultats]")

        time.sleep(1)   # politesse API CrossRef

    # Sauvegarde finale
    with open(OUTPUT_JSON_01, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\nTerminé — {len(results)}/{len(refs)} langues détectées → {OUTPUT_JSON_01}")

if __name__ == '__main__':
    main()