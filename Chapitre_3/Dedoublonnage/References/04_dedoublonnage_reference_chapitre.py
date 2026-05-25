"""
Détecte les doublons de références de type "chapitre" par similarité de
secondary_title et title, avec extraction du numéro de chapitre.

Pipeline :
  1. Récupération depuis MySQL + filtres.
  2. Groupement par secondary_title (Levenshtein ≥ SECONDARY_TITLE_THRESHOLD).
  3. Comparaison : même numéro de chapitre + titre nettoyé ≥ SIMILARITY_THRESHOLD.
  4. Union-Find pour la transitivité.
  5. Export JSON à vérifier avant fusion (keep / delete / skip).
"""

import json, re, unicodedata, itertools
import mysql.connector
from mysql.connector import Error as MySQLError
from collections import defaultdict
import Levenshtein
from typing import List, Dict, Tuple, Optional

DB_HOST     = 'localhost'
DB_USER     = 'root'
DB_PASSWORD = 'PASSWORD'
DB_NAME     = 'DATABASE'

FICHIER_SORTIE_JSON       = 'doublons_chapitres_a_verifier.json'
SECONDARY_TITLE_THRESHOLD = 0.80
SIMILARITY_THRESHOLD      = 0.90

ROMAN_TO_INT = {
    'I':1,'II':2,'III':3,'IV':4,'V':5,'VI':6,'VII':7,'VIII':8,'IX':9,'X':10,
    'XI':11,'XII':12,'XIII':13,'XIV':14,'XV':15,'XVI':16,'XVII':17,'XVIII':18,
    'XIX':19,'XX':20,'XXI':21,'XXII':22,'XXIII':23,'XXIV':24,'XXV':25,
}

WORD_TO_INT = {
    # Français
    'UN':1,'UNE':1,'DEUX':2,'TROIS':3,'QUATRE':4,'CINQ':5,'SIX':6,'SEPT':7,
    'HUIT':8,'NEUF':9,'DIX':10,'ONZE':11,'DOUZE':12,'TREIZE':13,'QUATORZE':14,
    'QUINZE':15,'SEIZE':16,'DIX-SEPT':17,'DIX-HUIT':18,'DIX-NEUF':19,'VINGT':20,
    'VINGT-ET-UN':21,'VINGT-DEUX':22,'VINGT-TROIS':23,'VINGT-QUATRE':24,'VINGT-CINQ':25,
    # Anglais
    'ONE':1,'TWO':2,'THREE':3,'FOUR':4,'FIVE':5,'SEVEN':7,'EIGHT':8,'NINE':9,
    'TEN':10,'ELEVEN':11,'TWELVE':12,'THIRTEEN':13,'FOURTEEN':14,'FIFTEEN':15,
    'SIXTEEN':16,'SEVENTEEN':17,'EIGHTEEN':18,'NINETEEN':19,'TWENTY':20,
    'TWENTY-ONE':21,'TWENTY-TWO':22,'TWENTY-THREE':23,'TWENTY-FOUR':24,'TWENTY-FIVE':25,
    # Allemand
    'EIN':1,'EINE':1,'ZWEI':2,'DREI':3,'VIER':4,'FUNF':5,
    'SECHS':6,'SIEBEN':7,'ACHT':8,'NEUN':9,'ZEHN':10,
    # Espagnol
    'UNO':1,'UNA':1,'DOS':2,'TRES':3,'CUATRO':4,'CINCO':5,
    'SEIS':6,'SIETE':7,'OCHO':8,'NUEVE':9,'DIEZ':10,
}

ROMANS = '|'.join(ROMAN_TO_INT)  # pattern réutilisable

CHAPTER_PATTERNS = [
    r'(CHAPITRE|CHAPTER|PART|PARTIE|TEIL|CAPITULO|TOME|VOLUME)\s*(\d+)',
    r'^\s*(\d+)[\s\.\:]',
    r'[\s\(](\d+)[\s\.\:\)]',
    rf'^({ROMANS})[\s\.\:]',
    rf'[\s\(]({ROMANS})[\s\.\:\)]',
]

REMOVAL_WORDS = set(
    ['CHAPITRE','CHAPTER','PART','PARTIE','TEIL','CAPITULO','TOME','VOLUME',
     'INTRO','INTRODUCTION','PREFACE','PROLOGUE','EPILOGUE',
     'ABBREVIATION','CONCLUSION','INDEX','APPENDIX']
    + list(ROMAN_TO_INT) + list(WORD_TO_INT)
)


# ---------------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------------

def normalize_text(text: Optional[str]) -> str:
    if not text:
        return ""
    text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('ASCII')
    text = re.sub(r'[^\w\s]', ' ', text.lower())
    return re.sub(r'\s+', ' ', text).strip()


def lev(t1: Optional[str], t2: Optional[str]) -> float:
    n1, n2 = normalize_text(t1), normalize_text(t2)
    return Levenshtein.ratio(n1, n2) if n1 and n2 else 0.0


def extract_chapter_number(title: Optional[str]) -> Optional[int]:
    if not title:
        return None
    s = normalize_text(title).upper()
    for pattern in CHAPTER_PATTERNS:
        m = re.search(pattern, s)
        if not m:
            continue
        val = m.group(2) if m.lastindex and m.lastindex >= 2 else m.group(1)
        if val.isdigit():
            n = int(val)
            if 1 <= n <= 25:
                return n
        if val in ROMAN_TO_INT:
            return ROMAN_TO_INT[val]
    for word, num in WORD_TO_INT.items():
        if re.search(r'\b' + re.escape(word) + r'\b', s):
            return num
    return None


def remove_chapter_indicators(title: Optional[str]) -> str:
    if not title:
        return ""
    words = normalize_text(title).upper().split()
    return ' '.join(
        w for w in words
        if w not in REMOVAL_WORDS and not (w.isdigit() and 1 <= int(w) <= 25)
    )


# ---------------------------------------------------------------------------
# Union-Find
# ---------------------------------------------------------------------------

class UnionFind:
    def __init__(self): self._p: Dict[int,int] = {}
    def find(self, x):
        self._p.setdefault(x, x)
        if self._p[x] != x: self._p[x] = self.find(self._p[x])
        return self._p[x]
    def union(self, x, y):
        rx, ry = self.find(x), self.find(y)
        if rx != ry: self._p[max(rx,ry)] = min(rx,ry)
    def clusters(self, ids):
        g: Dict[int,List[int]] = defaultdict(list)
        for i in ids: g[self.find(i)].append(i)
        return [v for v in g.values() if len(v) > 1]


#quelques références identifiées comme peu pertinentes à comparer, permet d'alléger le calcul
def get_filtered_references(cursor) -> List[Dict]: 
    cursor.execute("""
        SELECT * FROM reference
        WHERE secondary_title IS NOT NULL AND secondary_title != ''
          AND secondary_title NOT LIKE '%annal%'
          AND secondary_title NOT LIKE '%speculum%'
          AND secondary_title NOT LIKE '%object%'
          AND title NOT LIKE '%intro%'
          AND title NOT LIKE '%preface%'
          AND title NOT LIKE '%prologue%'
          AND title NOT LIKE '%epilogue%'
          AND title NOT LIKE '%abbrevia%'
          AND title NOT LIKE '%conclu%'
          AND secondary_title NOT LIKE '%Bridgeman%'
          AND title NOT LIKE '%index%'
          AND title NOT LIKE '%appendix%'
          AND title NOT LIKE '%rezension%'
          AND title NOT LIKE '%review%'
          AND title NOT LIKE '%droit%'
          AND secondary_title NOT LIKE '%american historical%'
        ORDER BY secondary_title, id
    """)
    return cursor.fetchall()


# ---------------------------------------------------------------------------
# Détection
# ---------------------------------------------------------------------------

def group_by_secondary_title(references: List[Dict]) -> List[Tuple[str, List[Dict]]]:
    groups: Dict[str, List[Dict]] = {}
    for ref in references:
        st = ref.get('secondary_title', '')
        if not st:
            continue
        norm = normalize_text(st)
        for key in groups:
            if lev(norm, normalize_text(key)) >= SECONDARY_TITLE_THRESHOLD:
                groups[key].append(ref)
                break
        else:
            groups[st] = [ref]
    return [(k, v) for k, v in groups.items() if len(v) > 1]


def find_duplicate_pairs(groups: List[Tuple[str, List[Dict]]]) -> List[Tuple[Dict, Dict]]:
    pairs = []
    for _key, refs in groups:
        by_chapter: Dict[int, List[Dict]] = defaultdict(list)
        for ref in refs:
            n = extract_chapter_number(ref.get('title'))
            if n is not None:
                by_chapter[n].append(ref)
        for group in by_chapter.values():
            if len(group) < 2:
                continue
            for r1, r2 in itertools.combinations(group, 2):
                t1 = remove_chapter_indicators(r1.get('title'))
                t2 = remove_chapter_indicators(r2.get('title'))
                if lev(t1, t2) >= SIMILARITY_THRESHOLD:
                    pairs.append((r1, r2))
    return pairs


def build_output(clusters: List[List[Dict]]) -> List[Dict]:
    output = []
    for cid, refs in enumerate(clusters, start=1):
        refs = sorted(refs, key=lambda r: r['id'])
        keep_id = refs[0]['id']
        output.append({
            "cluster_id": cid,
            "references": [
                {
                    "id":              r['id'],
                    "title":           r.get('title') or "",
                    "secondary_title": r.get('secondary_title') or "",
                    "year":            r.get('year'),
                    "action":          "keep" if r['id'] == keep_id else "delete",
                }
                for r in refs
            ],
        })
    return output


def main():
    try:
        conn   = mysql.connector.connect(host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME)
        cursor = conn.cursor(dictionary=True)
        print("Récupération des références...")
        references = get_filtered_references(cursor)
        cursor.close(); conn.close()
        print(f"{len(references)} références récupérées.")

        groups = group_by_secondary_title(references)
        print(f"Groupement : {len(groups)} groupe(s).")

        pairs = find_duplicate_pairs(groups)
        print(f"Détection : {len(pairs)} paire(s) trouvée(s).")

        uf, id_to_ref = UnionFind(), {}
        for r1, r2 in pairs:
            id_to_ref[r1['id']] = r1
            id_to_ref[r2['id']] = r2
            uf.union(r1['id'], r2['id'])

        clusters = [[id_to_ref[i] for i in cl] for cl in uf.clusters(list(id_to_ref))]
        print(f"Clusters : {len(clusters)} après transitivité.")

        output = build_output(clusters)
        with open(FICHIER_SORTIE_JSON, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2, default=str)

        total_sugg = sum(sum(1 for r in g['references'] if r['action'] == 'delete') for g in output)
        print(f"\nJSON exporté → {FICHIER_SORTIE_JSON}")
        print(f"{total_sugg} suppression(s) suggérée(s) sur {len(output)} cluster(s).")
        print("Vérifiez et ajustez les 'action' (keep/delete/skip) avant fusion.")

    except MySQLError as err:
        print(f"Erreur MySQL : {err}")


if __name__ == "__main__":
    main()