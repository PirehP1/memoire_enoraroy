"""
Script 02 – Détection de langue via la page web du DOI
Pour les références avec DOI mais sans résultat CrossRef (script 01).
Entrée  : base MySQL + resultats_01.json (IDs à exclure)
Sortie  : resultats_02.json  {id, langue, source_langue}
"""

import json
import re
import time
import requests
import mysql.connector
import spacy
from spacy.language import Language
from spacy_language_detection import LanguageDetector


DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'SQL2025Enora',
    'database': 'bibliographie',
    'charset': 'utf8mb4'
}

INPUT_JSON_01  = 'resultats_01.json'
OUTPUT_JSON_02 = 'resultats_02.json'

HEADERS = {'User-Agent': 'BiblioLangDetector/1.0 (Academic Research)'}

ACADEMIC_LANGUAGES = {
    'en', 'fr', 'de', 'it', 'es', 'pt', 'nl', 'pl', 'ru', 'ar', 'zh', 'ja',
    'tr', 'el', 'cs', 'ro', 'hu', 'sv', 'no', 'da', 'fi', 'uk',
    'ca', 'hr', 'sk', 'bg', 'lt', 'sl', 'et', 'lv',
    'ko', 'vi', 'th', 'id',
}


@Language.factory("language_detector")
def get_lang_detector(nlp, name):
    return LanguageDetector(seed=42)

nlp = spacy.load("en_core_web_sm")
nlp.add_pipe("language_detector", last=True)


def normalize(code) -> str | None:
    """Ramène un code brut (ex. 'en-US') à un code ISO court validé."""
    if not code or not isinstance(code, str):
        return None
    code = code.lower().strip().split('-')[0].split('_')[0]
    aliases = {'english': 'en', 'french': 'fr', 'german': 'de',
               'spanish': 'es', 'italian': 'it', 'arabic': 'ar',
               'chinese': 'zh', 'russian': 'ru', 'turkish': 'tr'}
    code = aliases.get(code, code)
    return code if code in ACADEMIC_LANGUAGES else None


def lang_from_html(html: str) -> str | None:
    """Extrait la langue depuis les balises meta standard."""
    for pat in [
        r'<meta\s+name=["\']DC\.language["\']\s+content=["\']([^"\']+)["\']',
        r'<meta\s+name=["\']citation_language["\']\s+content=["\']([^"\']+)["\']',
        r'<meta\s+(?:name|property)=["\'](?:language|lang)["\']\s+content=["\']([^"\']+)["\']',
        r'<html[^>]+lang=["\']([^"\']+)["\']',
    ]:
        m = re.search(pat, html, re.I)
        if m:
            lang = normalize(m.group(1))
            if lang:
                return lang
    return None


def lang_from_spacy(text: str) -> str | None:
    if not text or len(text) < 30:
        return None
    doc = nlp(text[:500])
    result = doc._.language
    if not isinstance(result, dict):
        return None
    code = result.get('language')
    return code if code in ACADEMIC_LANGUAGES else None

def fetch_html(url: str) -> tuple[str | None, str]:
    """
    Tente une requête GET, avec fallback SSL désactivé si nécessaire.
    Retourne (html, source_info) ou (None, erreur).
    """
    for verify in (True, False):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20,
                                allow_redirects=True, verify=verify)
            if resp.status_code == 200:
                return resp.text, 'ok'
            return None, f'http_error_{resp.status_code}'
        except requests.exceptions.SSLError:
            continue   # retry sans vérification SSL
        except requests.RequestException as e:
            return None, f'request_error: {e}'
    return None, 'ssl_error'


def detect_from_doi_page(doi: str, title: str) -> tuple[str | None, str]:
    """
    Détecte la langue pour un DOI donné.
    Ordre : meta HTML → spaCy sur corps de page.
    """

    html, status = fetch_html(f"https://doi.org/{doi}")
    if html is None:
        return None, status

    lang = lang_from_html(html)
    if lang:
        return lang, 'html_meta'

    # Fallback spaCy sur le texte brut de la page
    body = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html)).strip()
    lang = lang_from_spacy(body)
    if lang:
        return lang, 'spacy_page_content'

    return None, 'no_detection'

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    try:
        with open(INPUT_JSON_01, encoding='utf-8') as f:
            done_ids = {str(r['id']) for r in json.load(f)}
        print(f"{len(done_ids)} IDs exclus (script 01)")
    except FileNotFoundError:
        done_ids = set()
        print("Aucun fichier script 01 trouvé — aucune exclusion")

    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT id, title, doi
        FROM reference
        WHERE (language IS NULL OR language = '')
          AND doi IS NOT NULL AND doi != ''
        ORDER BY id
    """)
    refs = [r for r in cursor.fetchall() if str(r['id']) not in done_ids]
    cursor.close()
    conn.close()
    print(f"{len(refs)} références à traiter\n")

    results = []

    for i, ref in enumerate(refs, 1):
        title = (ref['title'] or '').strip()
        print(f"[{i}/{len(refs)}] ID {ref['id']} | {title[:60]}")

        lang, source = detect_from_doi_page(ref['doi'].strip(), title)

        results.append({'id': ref['id'], 'langue': lang or 'none', 'source_langue': source})
        print(f"  → {lang or 'none'} ({source})")

        if i % 10 == 0:
            with open(OUTPUT_JSON_02, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)

        time.sleep(1)

    with open(OUTPUT_JSON_02, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    detected = sum(1 for r in results if r['langue'] != 'none')
    print(f"\nTerminé — {detected}/{len(results)} langues détectées → {OUTPUT_JSON_02}")

if __name__ == '__main__':
    main()