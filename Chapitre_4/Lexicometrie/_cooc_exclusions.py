#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=======================================================================
  MODULE PARTAGÉ — SEGMENTS D'EXCLUSION POUR LES COOCCURRENCES
=======================================================================

Importez dans les scripts de cooccurrence :
  from _cooc_exclusions import EXCLUSION_SEGMENTS, is_excluded

RÈGLE : comparaison insensible à la casse, espaces multiples normalisés.
=======================================================================
"""

import re

EXCLUSION_SEGMENTS: list[tuple[str, str]] = [

    # ── Titres bibliographiques ──────────────────────────────────────
    ("Encyclopedia of Barbarian Europe",                    "titre_biblio"),
    ("The Body Legal in Barbarian Law",                     "titre_biblio"),
    ("Barbarian Tides",                                     "titre_biblio"),
    ("Narrators of Barbarian History",                      "titre_biblio"),
    ("On Barbarian Identity",                               "titre_biblio"),
    ("Barbarian Migrations and the Roman West",             "titre_biblio"),
    ("Barbarian Migrations and Chronik",                    "titre_biblio"),
    ("Integration of Barbarians in Late",                   "titre_biblio"),
    ("Barbarians and Politics at the Court",                "titre_biblio"),
    ("Captivity and Romano - Barbarian Interchange",        "titre_biblio"),
    ("Arian Barbarian Prospered",                           "titre_biblio"),
    ("Merciful Barbarians",                                 "titre_biblio"),
    ("Barbarian Incursion",                                 "titre_biblio"),
    ("Silver for the Barbarians",                           "titre_biblio"),
    ("Gold for the barbarians",                             "titre_biblio"),
    ("Ethnology of Europe 's Barbarians",                   "titre_biblio"),
    ("Education and Culture in the Barbarian West",         "titre_biblio"),
    ("Romans , Barbarians , and the Transformation",        "titre_biblio"),
    ("Le Barbare . Recherches",                             "titre_biblio"),
    ("Carolingian Chronicles",                              "titre_biblio"),
    ('The Theme of the "  Barbarian  Invasions " in Late Antique',  "titre_biblio"),
    ("The Theme of ' The  Barbarian  Invasions ' in Late Antique",  "titre_biblio"),
    ("Administrative Methods of  Barbarian  Settlement in the Fifth Century", "titre_biblio"),
    ("Barbarians  and Romans AD 418–584",                   "titre_biblio"),
    ("Barbarian  Migrations and the Birth of Medieval",     "titre_biblio"),
    ("The Technique of  Barbarian  Settlement in the Fifth Century", "titre_biblio"),
    ("Warfare and society in the  barbarian  west",         "titre_biblio"),
    ("Halsall ,  Barbarian  invasions",                     "titre_biblio"),
    ("Halsall , ' The  Barbarian  Invasions '",             "titre_biblio"),
    ("Halsall ,  Barbarian  Migrations",                    "titre_biblio"),
    ("Halsall , Guy , The  barbarian  invasions",           "titre_biblio"),
    ("Halsall ,  Barbarian  10 - 34",                       "titre_biblio"),
    ("The Map of the  Barbarian  Invasions : A Preliminary Report", "titre_biblio"),
    ("Heather , Empires and  Barbarians",                   "titre_biblio"),
    ("Genovefa of Paris and Brigit of Kildare Built Christianity in  Barbarian  Europe", "titre_biblio"),
    ("What 's Wrong with the Map of the  Barbarian  Invasions ?", "titre_biblio"),
    ("Rome , Constantinople , and the  Barbarians",         "titre_biblio"),
    ("Walter Goffart ,  Barbarians  and Romans",            "titre_biblio"),
    ("The Technique of  Barbarian  Settlement in the Fifth","titre_biblio"),
    ("Goffart ,  Barbarians  and Romans",                   "titre_biblio"),
    ("The  Barbarian  in Late Antiquity",                   "titre_biblio"),
    ("Empires and  barbarians",                             "titre_biblio"),
    ("Mathisen , \u201c Becoming Roman , Becoming  Barbarian  \u201d", "titre_biblio"),
    ("IS THERE HOPE FOR THE  BARBARIAN  ? IMAGINING OUTGROUP", "titre_biblio"),
    ("Heather , \u201c  Barbarian  in Late Antiquity \u201d","titre_biblio"),
    ("The '  barbarians  ' ( Heather 2006:191\u2013299 )", "titre_biblio"),
    ("Heather , Goths , pp . 340 - 41 .  Barbarian  Bishops","titre_biblio"),
    ("A New History of Rome and the  Barbarians",           "titre_biblio"),
    ("Pohl , ' Rome and the  Barbarians  '",                "titre_biblio"),
    ("Wells , The  Barbarian  Speaks",                      "titre_biblio"),
    ("Hen , Roman  Barbarians",                             "titre_biblio"),
    ("Von Rummel , Habitus  barbarus",                      "titre_biblio"),
    ("James , Europe 's  Barbarians",                       "titre_biblio"),
    ("Pohl , The  Barbarian  Challenge",                    "titre_biblio"),
    ("Steinacher , ' Who is the  Barbarian  ? '",           "titre_biblio"),
    ("' Who is the  Barbarian  ? Considerations",           "titre_biblio"),
    ("Understanding 6th\u2011century  barbarian  social organization and migration", "titre_biblio"),
    ("Roman Empire : a new history of Rome and the  barbarians", "titre_biblio"),
    ("Post - Roman Transitions : Christian and  Barbarian  Identities in Early Medieval Europe", "titre_biblio"),
    ("Peter S. , The  Barbarian  Speaks : How",             "titre_biblio"),
    ("Historische Barbarians  in Late Antiquity , W. Pohl", "titre_biblio"),
    ("Geary , \u201c  Barbarians  and Ethnicity \u201d",    "titre_biblio"),
    ("Vida , \u201c Many Identities of the  Barbarians  \u201d", "titre_biblio"),
    ("i Longobardi e l'Occidente  barbarico",               "titre_biblio"),
    ("PoHL , Gregorio Magno e i  barbari",                  "titre_biblio"),
    ('" Justinian and the  Barbarian  Kingdoms',            "titre_biblio"),
    ('" The  Barbarians  in Justinians Armies',             "titre_biblio"),
    ("Hadrill , The  Barbarian  West 400 - 1000",           "titre_biblio"),
    ("' The Conversion of the  Barbarians  '",              "titre_biblio"),
    ("Mathisen , \u201c Peregrini ,  Barbari",              "titre_biblio"),
    ("Mathisen , \u201c Violent Behavior and the Construction of  Barbarian identity in late Antiquity", "titre_biblio"),
    ("Legal Concepts and Patterns in the  Barbarians  ' Settlement on Roman", "titre_biblio"),
    ("Mathisen , Ralph W. \u201c ' Becoming Roman , Becoming  Barbarian  '", "titre_biblio"),
    ("Ralph W. Mathisen , Roman Aristocrats in  Barbarian Gaul", "titre_biblio"),
    ("Roman Citizenship and the Assimilation of  Barbarians  into the Late Roman World . \u201d", "titre_biblio"),
    ('Specimen Islandiae non  barbarae',                    "titre_biblio"),
    ('Barbarians  and Bishops',                             "titre_biblio"),
    ('Stroumsa ,  Barbarian  Philosophy',                   "titre_biblio"),
    ('K. Feld ,  Barbarische  \u2026',                      "titre_biblio"),
    ('HOW DID ALL THESE  BARBARIANS  GET HERE',             "titre_biblio"),
    ('Barbarians  at the Gates',                            "titre_biblio"),
    ('Barbarians  within the Gates of Rome',                "titre_biblio"),
    ("D. Sinor , ' Les  Barbares  ' , Diogene",             "titre_biblio"),
    ('Nye , \u201c The New Rome Meets the New  Barbarians  : How America Should Wield Its Power', "titre_biblio"),
    ('Peregrini ,  Barbari  , and Cives Romani : Concepts of Citizenship and the Legal Identity of  Barbarians  in the Later Roman Empire', "titre_biblio"),
    ('Romans ,  Barbarians  , and the Neil',                "titre_biblio"),
    ('The Frontier World . Romans ,  Barbarians  , and Military Culture', "titre_biblio"),
    ('The  Barbarian  Coinages as a Mirror of the',         "titre_biblio"),
    ("Barbari  's View",                                    "titre_biblio"),
    ('The Fading Power of Images : Romans ,  Barbarians  and the Uses of a Dichotomy in Early Medieval', "titre_biblio"),
    ('Barbarians  and Romans , 419\u2013584 : The Techniques', "titre_biblio"),
    ('Romans and  barbarians  : The decline of the',        "titre_biblio"),
    ('Romans ,  Barbarians  , and the ',                    "titre_biblio"),
    ('Barbarians  and Romans in North - West Europe from the', "titre_biblio"),
    ('Ethnicboundarymaking :  barbarians  , andtheusesofadichotomyinearly', "titre_biblio"),
    ('Romans ,  Barbarians  and Military Culture',          "titre_biblio"),
    ('Early Mediaeval  Barbarian  Elements in  Byzance',    "titre_biblio"),
    ('IMAGE OF THE  BARBARIAN  IN MEDIEVAL EUROPE',         "titre_biblio"),
    ('Barbarian  Bishops and the Churches',                 "titre_biblio"),
    ('Barbarian  Bishops ',                                 "titre_biblio"),
    ('Bishops ,  Barbarians  , and the',                    "titre_biblio"),
    ('eserciti  barbarici  nel periodo delle',              "titre_biblio"),
    ('Le invasioni  barbariche  e le origini delle',        "titre_biblio"),
    ('populi  barbari  avanti la loro venuta in Italia',    "titre_biblio"),
    ('Barbarea  vulgaris',                                  "titre_biblio"),
    ('Remembering the  Barbarian  Past',                    "titre_biblio"),
    ('A Study in the Structure of Sino -  Barbarian  Economic Relations', "titre_biblio"),
    ('GOTHIC  BARBARISM  OR GOLDEN AGE',                    "titre_biblio"),
    ('Rom und den  Barbaren  in der Historia Augusta',      "titre_biblio"),
    ('Rom und die  Barbaren',                               "titre_biblio"),
    ('Rom unddie  Barbaren',                                "titre_biblio"),
    ('dedicated to  Barbara  in Upper Hungary',             "titre_biblio"),
    ('Neglected  Barbarians',                               "titre_biblio"),
    ('MALMESBURY AND HIGH ECCLESIASTICISM IN A  BARBARIAN', "titre_biblio"),
    ('Cameron and Long ,  Barbarians  and Politics',        "titre_biblio"),
    ('Afterword : Neglecting the  Barbarian',               "titre_biblio"),
    ('353 - 354 .  Barbarian  : Vida',                      "titre_biblio"),

    # ── Bruit contextuel ────────────────────────────────────────────
    ('Barbara  - according to her legend ',                 "bruit"),
    ("Barbara  , Margaret ",                                "bruit"),
    ("Barbara  's and Katherine",                           "bruit"),
    ("Barbara  and Dorothy",                                "bruit"),
    ("Margaret and  Barbara ",                              "bruit"),
    ("Barbara  and Margaret.",                              "bruit"),
    ("Barbara  , Katherine",                                "bruit"),
    ("Barbara  and Katherine",                              "bruit"),
    ("St  Barbara",                                         "bruit"),

    # ── Prénom Barbara ───────────────────────────────────────────────
    ("Barbara Eileen Croken",   "prenom"),
    ("Barbarea  stricta Andrz", "prenom"),
    ("Barbara  Melchiori",      "prenom"),
    ("Barbara  Endicott",       "prenom"),
    ("Bell ,  Barbara",         "prenom"),
    ("Barbara  Haggh",          "prenom"),
    ("BARBARA  HAGGH ",         "prenom"),
    ("BARBARA  BELL",           "prenom"),
    ("Barbara  Harvey",         "prenom"),
    ("Harvey ,  Barbara",       "prenom"),
    ("Barbara  Newman",         "prenom"),
    ("Lewalski ,  Barbara",     "prenom"),
    ("Barbara Rogers",          "prenom"),
    ("Barbara Yorke",           "prenom"),
    ("Barbara Baert",           "prenom"),
    ("Barbara Rosenwein",       "prenom"),
    ("Barbara Harris",          "prenom"),
    ("Barbara Hanawalt",        "prenom"),
    ("Barbara Nani",            "prenom"),
    ("Barbara Cassin",          "prenom"),
    ("Barbara Maurmann",        "prenom"),
    ("Barbara Obrist",          "prenom"),
    ("Barbara  H. Rosenwein",   "prenom"),
    ("Rosenwein ,  Barbara",    "prenom"),
    ("Barbara  A . Hanawalt",   "prenom"),
    ("BARBARAA  . HANAWALT",    "prenom"),
    ("BARBARA  A. HANAWALT",    "prenom"),
    ("Barbara  Hillers",        "prenom"),
    ("BARBARA  HILLERS",        "prenom"),

    # ── Prénom Barbara — OCR collé ───────────────────────────────────
    ("BarbaraLepri",            "prenom_ocr"),
    ("BarbaraObrist",           "prenom_ocr"),
    ("BarbaraHarris",           "prenom_ocr"),
    ("barbarieromanitraantichitàeMedioEvo", "prenom_ocr"),

    # ── Toponyme ─────────────────────────────────────────────────────
    ("Santa Barbara",           "toponyme"),

    # ── Nom propre ───────────────────────────────────────────────────
    ("Barbarossa",              "nom_propre"),

    # ── Fragment latin ───────────────────────────────────────────────
    ("a barbaris",              "latin"),
]

BIB_TOKENS: list[str] = [
    # Chiffres romains courants dans les références
    "i", "ii",
    # Abréviations latines bibliographiques
    "ibid", "ibidem", "op", "cit", "loc", "cf", "sq", "sqq",
    "supra", "infra", "passim", "idem", "eadem", "ead",
    "et", "al", "ff",
    # Abréviations courantes
    "ed", "eds", "trans", "vol", "vols", "no", "nr",
    "fig", "figs", "tab", "pl", "pls",
    "ms", "mss",      # manuscrit(s)
    "fol", "fols",    # folio(s)
    "r", "v",         # recto / verso (après numéro de folio)
    "n", "fn",        # note, footnote (isolés)
    "ca", "c",        # circa
    "d", "b",         # died / born (dans les dates)
    "s", "ss",        # suivant(e)(s) en allemand / anglais
    "repr", "rev",    # reprint, revised
    "orig",           # original
    "anon",           # anonyme
    "me","my","myself","we","our","ours","ourselves","you","your","yours","yourself","yourselves","he","him","his","himself","she","her","hers","herself","it","its","itself","they","them","their","theirs","themselves","what","which","who","whom","this","that","these","those","am","is","are","was","were","be","been","being","have","has","had","having","do","does","did","doing","a","an","the","and","but","if","or","because","as","until","while","of","at","by","for","with","about","against","between","into","through","during","before","after","above","below","to","from","up","down","in","out","on","off","over","under","again","further","then","once","here","there","when","where","why","how","all","any","both","each","few","more","most","other","some","such","no","nor","not","only","own","same","so","than","too","very","s","t","can","will","just","don","should","now","historique","romain","lettre","ancien","études","et","est","qui","se","essai","si","romains","mythologie","pas","histoire","de","le","sur","politique","l'histoire","âge","nord","société","contre","ancienne","revue","gaule","française","vie","paris","chez","archéologique","quelques","rapport","documents","naissance","pierre","par","barbares","sociale","littérature","roi","droit","grande","mort","sous","français","societe","henri","à","french","pour","il","el","ne","cette","van","bibliothèque","copie","leur","papier","électronique","ces","d’un","être","conservation","haut","guizot","nous","roland","publie","tous","même","normandie","juridique","privé","chronique","fois","manuscrits","numérisation","gestion","francophone","données","comité","siècle","bibliothèque","sa","chanson","l’original","comité","recherches","médiévale","en","origines","recherche","lieux","michel","barbare","des","la","monde","au","du","les","moyen","romaine","temps","deux","langue","belge","d'un","que","sont","nationale","d’une","comme","f.m.","compte","québec","preuve","cet","bresc","dictionnaire","été","droz","peut","siècle","actes","livre","aux","d'une","à","une","y","numérique","âge","mais","authentique","d'apres","juin","danois","dans","nouvelle","xiie","siecle","pratique","entre","colloque","internationale","un","xve","travaux","mémoire","scientifique","littéraire","france","jean","ou","ce","dossier","xiiie","avec","premiere","mélanges","sicile","ils","forme","het","bibliotheque","archivistique","loi","javols","l’histoire", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m", "n", "o", "p", "q", "r", "s", "t", "u", "v", "w", "x", "y", "z",">","®",".","*","©","fol","/", "<", "í","]","gv", "7v", "î","p.","pp","ed","ii","ml","o","¿","em", "m","ï","ii","-","'","fig","ge'ez","[","]","ml","9v","°","eld","em","m","»","ii"
]


BIB_PATTERNS: list[str] = []

def _normalize(text: str) -> str:
    """Normalise : minuscules + espaces multiples collapsés."""
    return re.sub(r'\s+', ' ', text).lower().strip()
 
 
# Pré-calcul à l'import (évite de recalculer à chaque appel)
_SEGMENTS_NORM: list[tuple[str, str]] = [
    (_normalize(seg), cat) for seg, cat in EXCLUSION_SEGMENTS
]
 
_BIB_TOKENS_RE = re.compile(
    r"(?<!\w)(" + "|".join(re.escape(t) for t in BIB_TOKENS) + r")(?!\w)",
    re.IGNORECASE,
)
 
_BIB_PATTERNS_RE: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE | re.MULTILINE)
    for p in BIB_PATTERNS
]
 
 
def is_excluded(raw_context: str) -> tuple[bool, str]:
    """
    Teste si le contexte brut contient un segment d'exclusion.
    Retourne (True, catégorie) si exclus, (False, '') sinon.
    """
    ctx_norm = _normalize(raw_context)
    for seg_norm, cat in _SEGMENTS_NORM:
        if seg_norm in ctx_norm:
            return True, cat
    return False, ""
 
 
def clean_text_bib(text: str) -> str:
    """
    Applique le nettoyage sur un texte brut :
      1. Supprime les segments d'exclusion (EXCLUSION_SEGMENTS)
      2. Supprime les patterns bibliographiques (BIB_PATTERNS)
      3. Supprime les tokens courts isolés (BIB_TOKENS)
      4. Normalise les espaces
 
    Retourne le texte nettoyé.
    """
    # 1. Suppression des segments d'exclusion (insensible à la casse)
    for seg, _ in EXCLUSION_SEGMENTS:
        # On utilise re.escape pour gérer les caractères spéciaux
        pattern = re.compile(re.escape(seg), re.IGNORECASE)
        text = pattern.sub(" ", text)
 
    # 2. Suppression des patterns bibliographiques (ordre important)
    for pat in _BIB_PATTERNS_RE:
        text = pat.sub(" ", text)
 
    # 3. Suppression des tokens courts isolés
    text = _BIB_TOKENS_RE.sub(" ", text)
 
    # 4. Normalisation finale des espaces
    text = re.sub(r"\s+", " ", text).strip()
 
    return text
