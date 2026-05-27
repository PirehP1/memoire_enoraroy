"""
03_title_spacy.py
-----------------
Détection de langue par analyse du titre avec spaCy + spacy-language-detection.
Traite les références non résolues par les scripts 01 et 02.

Entrée  : base MySQL + resultats_01.json + resultats_02.json
Sortie  : resultats_03.json  [{id, langue, source_langue}]

Prérequis :
    pip install spacy spacy-language-detection langdetect
    python -m spacy download en_core_web_sm
"""

import json
import mysql.connector
import spacy
from spacy.language import Language
from spacy_language_detection import LanguageDetector

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'PASSWORD',
    'database': 'DATABASE',
    'charset': 'utf8mb4',
}

PREV_FILES  = ['resultats_01.json', 'resultats_02.json']
OUTPUT_FILE = 'resultats_03.json'

ACADEMIC_LANGUAGES = {
    'en', 'fr', 'de', 'it', 'es', 'pt', 'nl', 'pl', 'ru', 'ar', 'zh', 'ja',
    'tr', 'el', 'cs', 'ro', 'hu', 'sv', 'no', 'da', 'fi', 'uk',
    'ca', 'hr', 'sk', 'bg', 'lt', 'sl', 'et', 'lv',
    'ko', 'vi', 'th', 'id',
}

GENERIC_TITLES = {
    'introduction', 'conclusion', 'abstract', 'preface', 'foreword',
    'index', 'bibliography', 'references', 'contents', 'acknowledgments',
    'avant-propos', 'résumé',
}

# ---------------------------------------------------------------------------
# Initialisation du pipeline spaCy
# ---------------------------------------------------------------------------

@Language.factory("language_detector")
def get_lang_detector(nlp, name):
    return LanguageDetector(seed=42)

nlp = spacy.load("en_core_web_sm")
nlp.add_pipe('language_detector', last=True)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalize_lang(code) -> str | None:
    if not code or not isinstance(code, str):
        return None
    code = code.lower().strip().split('-')[0].split('_')[0]
    return code if code in ACADEMIC_LANGUAGES else None


def is_informative(text: str) -> bool:
    if not text:
        return False
    t = text.strip()
    return len(t) >= 9 and t.lower() not in GENERIC_TITLES


def detect_with_spacy(text: str) -> str | None:
    """Détecte la langue via spaCy + langdetect. Retourne None si score < 0.7."""
    doc = nlp(text)
    lang_info = doc._.language
    if not isinstance(lang_info, dict):
        return None
    code  = lang_info.get('language')
    score = lang_info.get('score', 0.0)
    if code and score >= 0.7:
        return normalize_lang(code)
    return None


def detect_language(title: str, secondary: str) -> tuple[str | None, str | None]:
    """
    Tente la détection sur le titre principal puis sur le titre secondaire.
    Retourne (code_langue, source) ou (None, None).
    """
    if is_informative(title):
        lang = detect_with_spacy(title)
        if lang:
            return lang, 'spacy'

    if is_informative(secondary):
        lang = detect_with_spacy(secondary)
        if lang:
            return lang, 'spacy'

    return None, None

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    resolved_ids: set = set()
    for path in PREV_FILES:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                resolved_ids.update(
                    r['id'] for r in json.load(f)
                    if r.get('langue') not in ('none', None, '')
                )
        except FileNotFoundError:
            pass
    print(f"{len(resolved_ids)} IDs déjà résolus (exclus).")

    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT id, title, secondary_title
        FROM reference
        WHERE language IS NULL OR language = ''
        ORDER BY id
    """)
    refs = [r for r in cursor.fetchall() if r['id'] not in resolved_ids]
    cursor.close()
    conn.close()
    print(f"{len(refs)} références à analyser par titre.\n")

    results = []
    for i, ref in enumerate(refs, 1):
        title = (ref['title'] or '').strip()
        sec   = (ref['secondary_title'] or '').strip()

        lang, source = detect_language(title, sec)

        if lang:
            results.append({'id': ref['id'], 'langue': lang, 'source_langue': source})
            print(f"[{i:>4}/{len(refs)}] ID {ref['id']:>6}  →  {lang:<6}  ({source})")
        else:
            print(f"[{i:>4}/{len(refs)}] ID {ref['id']:>6}  →  –")

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    failed = len(refs) - len(results)
    print(f"\n{len(results)}/{len(refs)} langues détectées  →  {OUTPUT_FILE}")
    if failed:
        print(f"{failed} références non résolues (passeront en révision manuelle)")

if __name__ == '__main__':
    main()