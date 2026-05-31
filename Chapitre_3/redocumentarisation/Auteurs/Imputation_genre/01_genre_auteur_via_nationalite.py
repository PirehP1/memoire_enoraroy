import requests
import json
import time
import re
import os
from pymongo import MongoClient
from typing import List, Dict

# ============================================================
# CONFIGURATION
# ============================================================
NAMSOR_API_KEY = "fbca864147e9233f078e3d9b6c74d1ab"
MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "references_biblio_mongo"
COLLECTION_NAME = "authors"

NAMSOR_URL = "https://v2.namsor.com/NamSorAPIv2/api2/json/genderFullGeoBatch"
NAMSOR_BATCH_SIZE = 100
WIKIDATA_USER_AGENT = "MongoDBAuthorGenderScript/1.1 enora.roy@etu.univ-paris1.fr"

# Fichiers locaux
OUTPUT_FILE = "auteurs_genres.jsonl"
PROGRESS_FILE = "progress.json"
ISO_CACHE_FILE = "iso_cache.json"  # <-- NOUVEAU CACHE

# ============================================================
# UTILITAIRES (Fichiers & Validation)
# ============================================================

def load_json_file(filepath: str, default_val=None):
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    return default_val if default_val is not None else {}

def save_json_file(filepath: str, data):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def append_jsonl(filepath: str, data: dict):
    with open(filepath, 'a', encoding='utf-8') as f:
        f.write(json.dumps(data, ensure_ascii=False) + '\n')

def validate_name_format(name: str) -> bool:
    if not name or not name.strip(): return False
    name = name.strip()
    
    reject_patterns = [r'^[A-Z]\.$', r'^[A-Z]\.\s*,', r'^[A-Z]\.\s+\w+$', r'^\w+\s+[A-Z]\.$', r'^\w+,\s*[A-Z]\.$']
    if any(re.match(p, name, re.IGNORECASE) for p in reject_patterns): return False
    
    if re.search(r'[A-Z]\.', name) and not re.search(r'[A-Z]\.\s+[A-Za-z]{2,}', name): return False
    
    words = [w for w in re.split(r'[,\s]+', name) if len(w) >= 2 and not w.endswith('.')]
    return len(words) >= 1

# ============================================================
# WIKIDATA & ISO CODES (Avec Cache)
# ============================================================

def fetch_iso_from_wikidata(country_name: str) -> str:
    """Recherche le code ISO sur Wikidata (simplifié)."""
    search_url = "https://www.wikidata.org/w/api.php"
    headers = {"User-Agent": WIKIDATA_USER_AGENT}
    
    # Étape 1 : Trouver l'ID du pays
    resp = requests.get(search_url, headers=headers, timeout=10, params={
        "action": "wbsearchentities", "format": "json", "language": "fr", "type": "item", "search": country_name, "limit": 3
    }).json()
    
    if not resp.get('search'): return None
    country_id = resp['search'][0]['id'] # On prend le premier par simplicité
    time.sleep(0.3)
    
    # Étape 2 : Récupérer le claim P297 (ISO 3166-1 alpha-2)
    resp = requests.get(search_url, headers=headers, timeout=10, params={
        "action": "wbgetentities", "format": "json", "ids": country_id, "props": "claims"
    }).json()
    
    try:
        return resp['entities'][country_id]['claims']['P297'][0]['mainsnak']['datavalue']['value']
    except KeyError:
        return None

def get_iso_code(country_name: str, cache: dict) -> str:
    """Vérifie le cache local avant de taper sur l'API Wikidata."""
    if country_name in cache:
        return cache[country_name]
    
    print(f"DEBUG: Appel Wikidata pour un nouveau pays -> {country_name}")
    iso_code = fetch_iso_from_wikidata(country_name)
    cache[country_name] = iso_code
    save_json_file(ISO_CACHE_FILE, cache) # Sauvegarde immédiate
    time.sleep(1)
    return iso_code

# ============================================================
# MAIN PIPELINE
# ============================================================

def process_batch(batch: List[dict], auteur_map: dict, processed_ids: set):
    """Envoie le batch à NamSor et sauvegarde les résultats."""
    if not batch: return
    
    print(f"DEBUG: Envoi d'un batch de {len(batch)} noms à NamSor...")
    headers = {"X-API-KEY": NAMSOR_API_KEY, "Accept": "application/json", "Content-Type": "application/json"}
    
    try:
        response = requests.post(NAMSOR_URL, json={"personalNames": batch}, headers=headers, timeout=30)
        if response.status_code != 200:
            print(f"DEBUG: Erreur NamSor {response.status_code}: {response.text}")
            return

        for result in response.json().get('personalNames', []):
            req_id = result.get('id')
            if req_id not in auteur_map: continue
            
            auteur_id, pays = auteur_map[req_id]
            genre = result.get('likelyGender')
            
            # Sauvegarde du résultat
            append_jsonl(OUTPUT_FILE, {
                'auteur_id': auteur_id,
                'genre_identifie': genre,
                'namsor_results': [{'pays': pays, 'namsor_result': result}]
            })
            
            processed_ids.add(auteur_id)
            
    except Exception as e:
        print(f"DEBUG: Exception NamSor: {e}")

def main():
    
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    
    progress = load_json_file(PROGRESS_FILE, {"processed_ids": []})
    processed_ids = set(progress.get("processed_ids", []))
    iso_cache = load_json_file(ISO_CACHE_FILE)
    
    query = {
            'nationalites.nom_pays': {'$exists': True, '$ne': None},
            '$or': [
                {'genre': {'$exists': False}},
                {g'genre.valeur': {'$exists': False}},
                {'genre.valeur': {'$in': [None, '', ' ']}}
            ],
            '_id': {'$nin': list(processed_ids)} if processed_ids else {'$exists': True}
        }

    # Utilisation d'un curseur plutôt que list() pour économiser la RAM
    cursor = db[COLLECTION_NAME].find(query)
    
    current_batch = []
    auteur_map = {}
    
    for auteur in cursor:
        auteur_id = str(auteur['_id'])
        prenom = auteur.get('nom_complet', '').strip()
        
        if not validate_name_format(prenom): continue
        
        for nat in auteur.get('nationalites', []):
            if not isinstance(nat, dict): continue
            nom_pays = nat.get('nom_pays')
            if not nom_pays: continue
            
            iso_code = get_iso_code(nom_pays, iso_cache)
            if not iso_code: continue
            
            req_id = f"{auteur_id}_{iso_code}"
            current_batch.append({"id": req_id, "name": prenom, "countryIso2": iso_code})
            auteur_map[req_id] = (auteur_id, nom_pays)
            
            # Dès qu'on atteint 100, on envoie le batch
            if len(current_batch) >= NAMSOR_BATCH_SIZE:
                process_batch(current_batch, auteur_map, processed_ids)
                save_json_file(PROGRESS_FILE, {"processed_ids": list(processed_ids)})
                current_batch = []
                auteur_map = {}
                time.sleep(0.5)
                
    # Traiter le reste du dernier batch
    if current_batch:
        process_batch(current_batch, auteur_map, processed_ids)
        save_json_file(PROGRESS_FILE, {"processed_ids": list(processed_ids)})

    print(f"\nTerminé ! {len(processed_ids)} auteurs traités au total.")

if __name__ == "__main__":
    main()